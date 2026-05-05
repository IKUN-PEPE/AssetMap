from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy import func, inspect, text
from sqlalchemy.orm import Session
from urllib.parse import quote
import httpx
import ipaddress
import socket
from app.core.db import get_db
from app.models.exposure_search import ExposureSearchTask, ExposureSearchResult
from app.schemas.exposure_search import (
    BatchDeleteExposureResults,
    BatchDeleteExposureTasks,
    ExposureSearchTaskCreate,
    ExposureSearchTaskSchema,
    ExposureSearchResultSchema,
    BatchUpdateExposureResults,
    ConfirmImportExposureResults,
    RetryExposureQueryRequest,
)
from app.services.exposure_search import ExposureSearchService
from app.tasks.collect_persistence import save_assets
import asyncio
import logging
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

router = APIRouter()
_EXPOSURE_SCHEMA_CHECKED_ENGINES: set[str] = set()

DOCUMENT_FILE_TYPES = {"pdf", "doc", "docx", "xls", "xlsx", "sql"}
CLUE_HOST_MARKERS = ("github.com", "pan.baidu.com")
OFFICE_PREVIEW_FILE_TYPES = {"doc", "docx", "xls", "xlsx", "ppt", "pptx"}
TEXT_PREVIEW_FILE_TYPES = {"csv", "sql", "json"}


def classify_result_import_type(url: str, file_type: str | None) -> str:
    normalized_url = (url or "").strip().lower()
    normalized_type = (file_type or "").strip().lower()
    if not normalized_url.startswith("http"):
        return "clue"
    if normalized_type in DOCUMENT_FILE_TYPES:
        return "clue"
    if any(marker in normalized_url for marker in CLUE_HOST_MARKERS):
        return "clue"
    return "asset"


def build_result_preview_url(url: str, file_type: str | None) -> str | None:
    normalized_url = (url or "").strip()
    normalized_type = (file_type or "").strip().lower()
    if not normalized_url.startswith(("http://", "https://")):
        return None
    if normalized_type not in OFFICE_PREVIEW_FILE_TYPES:
        return None
    return f"https://view.officeapps.live.com/op/view.aspx?src={quote(normalized_url, safe='')}"


def build_text_preview_url(url: str, file_type: str | None) -> str | None:
    normalized_url = (url or "").strip()
    normalized_type = (file_type or "").strip().lower()
    if not normalized_url.startswith(("http://", "https://")):
        return None
    if normalized_type not in TEXT_PREVIEW_FILE_TYPES:
        return None
    return f"/api/v1/exposure-search/preview-text?url={quote(normalized_url, safe='')}&file_type={quote(normalized_type, safe='')}"


def _is_public_preview_target(url: str) -> bool:
    try:
        parsed = httpx.URL(url)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.host
    if not host:
        return False
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, None)}
    except Exception:
        return False
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
    return True


def ensure_exposure_search_schema_columns(db: Session) -> None:
    bind = getattr(db, "bind", None)
    if bind is None:
        return

    engine_key = str(getattr(bind, "url", ""))
    if engine_key in _EXPOSURE_SCHEMA_CHECKED_ENGINES:
        return

    inspector = inspect(bind)
    try:
        tables = set(inspector.get_table_names())
    except Exception:
        return
    if "exposure_search_tasks" not in tables:
        _EXPOSURE_SCHEMA_CHECKED_ENGINES.add(engine_key)
        return

    columns = {item["name"] for item in inspector.get_columns("exposure_search_tasks")}
    statements: list[str] = []
    if "max_results" not in columns:
        statements.append("ALTER TABLE exposure_search_tasks ADD COLUMN max_results INTEGER DEFAULT 100")
    if "max_pages" not in columns:
        statements.append("ALTER TABLE exposure_search_tasks ADD COLUMN max_pages INTEGER DEFAULT 2")
    if "only_documents" not in columns:
        statements.append("ALTER TABLE exposure_search_tasks ADD COLUMN only_documents BOOLEAN DEFAULT FALSE")
    if "only_webpages" not in columns:
        statements.append("ALTER TABLE exposure_search_tasks ADD COLUMN only_webpages BOOLEAN DEFAULT FALSE")

    if statements:
        for statement in statements:
            db.execute(text(statement))
        db.commit()

    _EXPOSURE_SCHEMA_CHECKED_ENGINES.add(engine_key)


def _build_task_query_plan_payload(db: Session, task: ExposureSearchTask) -> list[dict]:
    plan = [dict(item or {}) for item in (task.query_plan if isinstance(task.query_plan, list) else [])]
    bind = getattr(db, "bind", None)
    if bind is None:
        return plan
    inspector = inspect(bind)
    try:
        tables = set(inspector.get_table_names())
    except Exception:
        return plan
    if "exposure_search_results" not in tables:
        return plan
    rows = (
        db.query(ExposureSearchResult.query, func.count(ExposureSearchResult.id))
        .filter(ExposureSearchResult.task_id == task.id)
        .group_by(ExposureSearchResult.query)
        .all()
    )
    counts = {str(query or ""): int(count or 0) for query, count in rows}
    seen_queries: set[str] = set()

    for item in plan:
        query_text = str(item.get("query") or "")
        item["results_count"] = counts.get(query_text, 0)
        seen_queries.add(query_text)

    for query_text, count in counts.items():
        if not query_text or query_text in seen_queries:
            continue
        plan.append(
            {
                "query": query_text,
                "status": "completed",
                "results_count": count,
            }
        )

    return plan


def _serialize_task(db: Session, task: ExposureSearchTask) -> ExposureSearchTaskSchema:
    payload = ExposureSearchService.build_task_schema(task)
    query_plan = _build_task_query_plan_payload(db, task)
    payload.query_plan = query_plan

    total_queries = len(query_plan)
    completed_queries = sum(1 for item in query_plan if (item or {}).get("status") in {"completed", "stopped", "failed"})
    current_query = None if task.status in {"completed", "stopped", "failed"} else next(
        ((item or {}).get("query") for item in query_plan if (item or {}).get("status") == "running"),
        None,
    )
    next_query = None if task.status in {"completed", "stopped", "failed"} else next(
        ((item or {}).get("query") for item in query_plan if (item or {}).get("status") == "pending"),
        None,
    )
    progress_percent = int((completed_queries / total_queries) * 100) if total_queries else 0
    if task.status == "completed" and total_queries > 0:
        progress_percent = 100

    payload.current_query = current_query
    payload.next_query = next_query
    payload.completed_queries = completed_queries
    payload.total_queries = total_queries
    payload.progress_percent = progress_percent
    return payload

@router.post("/tasks", response_model=ExposureSearchTaskSchema)
async def create_task(
    payload: ExposureSearchTaskCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    ensure_exposure_search_schema_columns(db)
    task = ExposureSearchTask(
        name=payload.name,
        org_keywords=payload.org_keywords,
        title_keywords=payload.title_keywords,
        url_keywords=payload.url_keywords,
        file_types=payload.file_types,
        sources=payload.sources,
        max_results=payload.max_results,
        max_pages=payload.max_pages,
        only_documents=payload.only_documents,
        only_webpages=payload.only_webpages,
        status="pending"
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    if payload.auto_run:
        # Use the explicit headless parameter
        service = ExposureSearchService(db, headless=payload.headless)
        background_tasks.add_task(service.run_task, task.id)

    return task

@router.get("/tasks", response_model=list[ExposureSearchTaskSchema])
def list_tasks(db: Session = Depends(get_db)):
    ensure_exposure_search_schema_columns(db)
    tasks = db.query(ExposureSearchTask).order_by(ExposureSearchTask.created_at.desc()).all()
    return [_serialize_task(db, task) for task in tasks]

@router.get("/tasks/{task_id}", response_model=ExposureSearchTaskSchema)
def get_task(task_id: str, db: Session = Depends(get_db)):
    ensure_exposure_search_schema_columns(db)
    ExposureSearchService.sync_task_counts(db, task_id)
    task = db.query(ExposureSearchTask).filter(ExposureSearchTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return _serialize_task(db, task)

@router.get("/tasks/{task_id}/results", response_model=list[ExposureSearchResultSchema])
def list_results(
    task_id: str,
    status: str | None = None,
    db: Session = Depends(get_db)
):
    ensure_exposure_search_schema_columns(db)
    query = db.query(ExposureSearchResult).filter(ExposureSearchResult.task_id == task_id)
    if status:
        query = query.filter(ExposureSearchResult.status == status)
    results = query.order_by(ExposureSearchResult.created_at.desc()).all()
    payload = []
    for item in results:
        schema_item = ExposureSearchResultSchema.model_validate(item)
        schema_item.preview_url = build_result_preview_url(item.url, item.file_type) or build_text_preview_url(item.url, item.file_type)
        payload.append(schema_item)
    return payload


@router.get("/preview-text", response_class=HTMLResponse)
async def preview_text_file(url: str, file_type: str | None = None):
    normalized_type = (file_type or "").strip().lower()
    if normalized_type not in TEXT_PREVIEW_FILE_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported text preview type")
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid preview URL")
    if not _is_public_preview_target(url):
        raise HTTPException(status_code=400, detail="Unsafe preview target")

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            response = await client.get(url)
            response.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch preview content: {exc}") from exc

    try:
        content = response.content.decode("utf-8")
    except UnicodeDecodeError:
        content = response.content.decode("utf-8", errors="replace")

    escaped = (
        content.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    title = f"AssetMap Preview - {normalized_type.upper()}"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <style>
    body {{
      margin: 0;
      font-family: Consolas, "Courier New", monospace;
      background: #0f172a;
      color: #e2e8f0;
    }}
    header {{
      position: sticky;
      top: 0;
      padding: 12px 16px;
      background: #111827;
      border-bottom: 1px solid #334155;
      font-family: Arial, sans-serif;
      z-index: 1;
    }}
    .meta {{
      font-size: 12px;
      color: #94a3b8;
      word-break: break-all;
    }}
    pre {{
      margin: 0;
      padding: 16px;
      white-space: pre-wrap;
      word-break: break-word;
      line-height: 1.5;
      font-size: 13px;
    }}
  </style>
</head>
<body>
  <header>
    <div>{title}</div>
    <div class="meta">{url}</div>
  </header>
  <pre>{escaped}</pre>
</body>
</html>"""

@router.post("/results/batch-update")
def batch_update_results(payload: BatchUpdateExposureResults, db: Session = Depends(get_db)):
    ensure_exposure_search_schema_columns(db)
    results = db.query(ExposureSearchResult).filter(ExposureSearchResult.id.in_(payload.ids)).all()
    task_ids = set()
    for res in results:
        res.status = payload.status
        task_ids.add(res.task_id)
    db.commit()
    for tid in task_ids:
        ExposureSearchService.sync_task_counts(db, tid)
    return {"message": f"Updated {len(results)} results"}


@router.post("/results/batch-delete")
def batch_delete_results(payload: BatchDeleteExposureResults, db: Session = Depends(get_db)):
    ensure_exposure_search_schema_columns(db)
    results = db.query(ExposureSearchResult).filter(ExposureSearchResult.id.in_(payload.ids)).all()
    task_ids = {res.task_id for res in results}
    deleted_count = len(results)

    for res in results:
        db.delete(res)
    db.commit()

    for tid in task_ids:
        ExposureSearchService.sync_task_counts(db, tid)
    return {"message": f"Deleted {deleted_count} results", "deleted": deleted_count}


@router.post("/tasks/{task_id}/confirm-import")
async def confirm_import(
    task_id: str,
    payload: ConfirmImportExposureResults,
    db: Session = Depends(get_db)
):
    ensure_exposure_search_schema_columns(db)
    task = db.query(ExposureSearchTask).filter(ExposureSearchTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    query = db.query(ExposureSearchResult).filter(ExposureSearchResult.task_id == task_id)
    if payload.import_all_valid:
        query = query.filter(ExposureSearchResult.status == "valid")
    else:
        query = query.filter(ExposureSearchResult.id.in_(payload.ids))

    results = query.all()
    if not results:
        return {"message": "No results to import"}

    web_records = []
    importable_results: list[ExposureSearchResult] = []
    clue_count = 0
    for res in results:
        if classify_result_import_type(res.url, res.file_type) == "asset":
            web_records.append({
                "url": res.url,
                "title": res.title,
                "source": f"exposure_search:{res.source}",
                "raw_payload": res.raw_payload
            })
            importable_results.append(res)
            res.status = "imported"
            task.imported_count += 1
        else:
            res.status = "valid"
            clue_count += 1

    if web_records:
        try:
            from app.models.job import CollectJob
            import uuid
            # Create a formal CollectJob to satisfy constraints and maintain audit log
            import_job = CollectJob(
                id=str(uuid.uuid4()),
                job_name=f"Exposure Import: {task.name}",
                sources={"exposure_search": True},
                query_payload={"task_id": task.id},
                status="completed",
                dedup_strategy="overwrite",
                created_at=datetime.utcnow(),
                started_at=datetime.utcnow(),
                finished_at=datetime.utcnow()
            )
            db.add(import_job)
            db.commit()
            
            save_result = save_assets(db, import_job, web_records, "exposure_search")
            for res, asset_id in zip(importable_results, getattr(save_result, "saved_asset_ids", [])):
                res.imported_asset_id = asset_id
        except Exception as e:
            logger.error(f"Failed to import assets: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Asset import failed: {str(e)}")

    db.commit()
    ExposureSearchService.sync_task_counts(db, task_id)
    return {
        "message": f"Processed {len(results)} results: {len(web_records)} imported as assets, {clue_count} marked as valid clues."
    }

@router.post("/tasks/{task_id}/stop")
def stop_task(task_id: str, db: Session = Depends(get_db)):
    ensure_exposure_search_schema_columns(db)
    logger.info(f"Stopping task {task_id}")
    task = db.query(ExposureSearchTask).filter(ExposureSearchTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.status == "running":
        task.status = "stopping"
        db.commit()
        logger.info(f"Task {task_id} status set to stopping")
        return {"message": "Stopping instruction sent", "status": "stopping"}
    
    return {"message": f"Task is in {task.status} state and cannot be stopped", "status": task.status}


@router.post("/tasks/{task_id}/retry-query")
async def retry_query(task_id: str, payload: RetryExposureQueryRequest, db: Session = Depends(get_db)):
    ensure_exposure_search_schema_columns(db)
    task = db.query(ExposureSearchTask).filter(ExposureSearchTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    service = ExposureSearchService(db, headless=True)
    await service.retry_query(task_id, payload.query)
    refreshed = db.query(ExposureSearchTask).filter(ExposureSearchTask.id == task_id).first()
    if not refreshed:
        raise HTTPException(status_code=404, detail="Task not found after retry")
    return _serialize_task(db, refreshed)


@router.post("/tasks/batch-delete")
def batch_delete_tasks(payload: BatchDeleteExposureTasks, db: Session = Depends(get_db)):
    ensure_exposure_search_schema_columns(db)
    tasks = db.query(ExposureSearchTask).filter(ExposureSearchTask.id.in_(payload.ids)).all()
    deleted_count = len(tasks)
    for task in tasks:
        db.delete(task)
    db.commit()
    return {"message": f"Deleted {deleted_count} tasks", "deleted": deleted_count}


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str, db: Session = Depends(get_db)):
    ensure_exposure_search_schema_columns(db)
    task = db.query(ExposureSearchTask).filter(ExposureSearchTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()
    return {"message": "Task deleted"}
