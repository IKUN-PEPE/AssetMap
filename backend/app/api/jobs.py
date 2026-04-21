from typing import Any, List
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Query
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from app.api.assets import serialize_asset
from app.core.config import BASE_DIR
from app.core.db import get_db
from app.core.huey import run_in_process
from app.models import CollectJob, SourceObservation, WebEndpoint
from app.schemas.job import (
    CollectJobCreate,
    CollectJobDetail,
    CollectJobRead,
    JobLogResponse,
    JobResultPreviewResponse,
    JobTaskDetails,
)
from app.services.collectors.preview import get_csv_preview
from app.services.normalizer.service import normalize_url
from app.tasks.sample_import import import_sample_assets

router = APIRouter()
logger = logging.getLogger(__name__)

UPLOAD_DIR = BASE_DIR / "tmp_uploads"
LOGS_DIR = BASE_DIR / "logs"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)


def construct_command_line(job: CollectJob) -> str:
    if "csv_import" in job.sources:
        source_type = (job.query_payload or {}).get("source_type") or "mapped"
        return f"import --source {source_type} --file {(job.query_payload or {}).get('file_path', '')}"

    commands = []
    queries = (job.query_payload or {}).get("queries", [])
    for q_item in queries:
        source = q_item.get("source")
        query = q_item.get("query")
        if source and query:
            commands.append(f'{source} --query "{query}"')
    return " | ".join(commands)


def _get_job_or_404(db: Session, job_id: str) -> CollectJob:
    job = db.get(CollectJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _get_log_content(job_id: str) -> tuple[str, bool]:
    log_file = LOGS_DIR / f"{job_id}.log"
    if not log_file.exists():
        return "", False
    return log_file.read_text(encoding="utf-8", errors="replace"), True


def _stage_state(*, enabled: bool, started: bool, finished: bool, success_count: int, failed_count: int) -> str:
    if not enabled:
        return "disabled"
    if not started:
        return "pending"
    if started and not finished:
        return "running"
    if success_count > 0 and failed_count > 0:
        return "partial_failed"
    if success_count > 0:
        return "success"
    if failed_count > 0:
        return "failed"
    return "failed"


def _extract_last_stage_error(log_content: str, marker: str) -> str | None:
    last_error = None
    for line in log_content.splitlines():
        if marker not in line:
            continue
        if " reason=" in line:
            last_error = line.split(" reason=", 1)[1].strip() or None
    return last_error



def _summarize_task_details(
    job: CollectJob,
    log_content: str,
    db: Session,
    *,
    result_asset_count: int | None = None,
) -> JobTaskDetails:
    observations_count = (
        db.query(SourceObservation)
        .filter(SourceObservation.collect_job_id == job.id)
        .count()
    )
    if result_asset_count is None:
        result_asset_count = len(_collect_result_assets(job.id, db))
    verify_started = "Auto verify start" in log_content
    verify_finished = "Verify post-process finished" in log_content or "Auto verify finished" in log_content
    overall_finished = "Auto verify finished" in log_content
    screenshot_started = "Screenshot post-process start" in log_content
    screenshot_finished = "Screenshot post-process finished" in log_content or overall_finished
    screenshot_success = log_content.count("Screenshot success")
    screenshot_failed = log_content.count("Screenshot failed")
    verify_success = log_content.count("Verify success")
    verify_failed = log_content.count("Verify failed")
    verify_last_error = _extract_last_stage_error(log_content, "Verify failed")
    screenshot_last_error = _extract_last_stage_error(log_content, "Screenshot failed")
    verify_state = _stage_state(
        enabled=bool(job.auto_verify),
        started=verify_started,
        finished=verify_finished,
        success_count=verify_success,
        failed_count=verify_failed,
    )
    screenshot_state = _stage_state(
        enabled=bool(job.auto_verify),
        started=screenshot_started,
        finished=screenshot_finished,
        success_count=screenshot_success,
        failed_count=screenshot_failed,
    )
    post_process_state = _stage_state(
        enabled=bool(job.auto_verify),
        started=verify_started or screenshot_started,
        finished=overall_finished,
        success_count=verify_success + screenshot_success,
        failed_count=verify_failed + screenshot_failed,
    )

    return JobTaskDetails.model_validate(
        {
            "collection": {
                "status": job.status,
                "progress": job.progress,
                "observation_count": observations_count,
                "result_asset_count": result_asset_count,
            },
            "post_process": {
                "enabled": bool(job.auto_verify),
                "state": post_process_state,
                "verify": {
                    "state": verify_state,
                    "started": verify_started,
                    "finished": verify_finished,
                    "success": verify_success,
                    "failed": verify_failed,
                    "last_error": verify_last_error,
                },
                "screenshot": {
                    "state": screenshot_state,
                    "started": screenshot_started,
                    "finished": screenshot_finished,
                    "success": screenshot_success,
                    "failed": screenshot_failed,
                    "last_error": screenshot_last_error,
                },
            },
        }
    )


def _normalize_candidate_url(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return normalize_url(raw)
    except Exception:
        return raw


def _observation_candidate_keys(obs: SourceObservation) -> dict[str, Any]:
    raw_payload = obs.raw_payload or {}
    return {
        "web_endpoint_id": raw_payload.get("web_endpoint_id") or raw_payload.get("id"),
        "source_record_id": getattr(obs, "source_record_id", None) or raw_payload.get("source_record_id"),
        "normalized_url": _normalize_candidate_url(
            raw_payload.get("normalized_url")
            or raw_payload.get("fallback_url")
            or raw_payload.get("url")
        ),
        "asset_identity_key": raw_payload.get("asset_identity_key"),
        "domain": raw_payload.get("resolved_domain") or raw_payload.get("domain"),
        "host": raw_payload.get("resolved_host") or raw_payload.get("host"),
        "ip": raw_payload.get("resolved_ip") or raw_payload.get("ip"),
        "port": raw_payload.get("resolved_port") or raw_payload.get("port"),
    }


def _build_result_lookup_indexes(assets: list[WebEndpoint]) -> dict[str, dict[Any, WebEndpoint]]:
    by_id: dict[Any, WebEndpoint] = {}
    by_url: dict[Any, WebEndpoint] = {}
    by_identity: dict[Any, WebEndpoint] = {}
    by_source_record: dict[Any, WebEndpoint] = {}
    by_domain_port: dict[Any, WebEndpoint] = {}
    by_ip_port: dict[Any, WebEndpoint] = {}
    by_host_port: dict[Any, WebEndpoint] = {}
    by_domain: dict[Any, WebEndpoint] = {}
    by_ip: dict[Any, WebEndpoint] = {}
    by_host: dict[Any, WebEndpoint] = {}

    for asset in assets:
        by_id[asset.id] = asset

        raw_url = getattr(asset, "normalized_url", None)
        if raw_url:
            by_url[raw_url] = asset
            normalized_lookup_url = _normalize_candidate_url(raw_url)
            if normalized_lookup_url:
                by_url[normalized_lookup_url] = asset

        source_meta = getattr(asset, "source_meta", {}) or {}
        service = getattr(asset, "service", None)
        host_obj = getattr(service, "host", None) if service else getattr(asset, "host", None)
        domain = getattr(asset, "domain", None) or source_meta.get("domain")
        ip = (getattr(host_obj, "ip", None) if host_obj else None) or source_meta.get("ip")
        port = (getattr(service, "port", None) if service else None) or source_meta.get("port")
        if port is not None:
            try:
                port = int(port)
            except (TypeError, ValueError):
                port = None
        identity_key = source_meta.get("asset_identity_key")
        if identity_key:
            by_identity[identity_key] = asset
        source_record_id = source_meta.get("source_record_id")
        if source_record_id:
            by_source_record[source_record_id] = asset
        host = source_meta.get("host") or source_meta.get("subdomain") or domain or ip

        if domain:
            by_domain[domain] = asset
        if ip:
            by_ip[ip] = asset
        if host:
            by_host[host] = asset
        if domain and port is not None:
            by_domain_port[(domain, port)] = asset
        if ip and port is not None:
            by_ip_port[(ip, port)] = asset
        if host and port is not None:
            by_host_port[(host, port)] = asset

    return {
        "by_id": by_id,
        "by_url": by_url,
        "by_identity": by_identity,
        "by_source_record": by_source_record,
        "by_domain_port": by_domain_port,
        "by_ip_port": by_ip_port,
        "by_host_port": by_host_port,
        "by_domain": by_domain,
        "by_ip": by_ip,
        "by_host": by_host,
    }


def _resolve_asset_from_observation(obs: SourceObservation, indexes: dict[str, dict[Any, WebEndpoint]]) -> WebEndpoint | None:
    keys = _observation_candidate_keys(obs)
    candidate = None
    if keys["web_endpoint_id"]:
        candidate = indexes["by_id"].get(keys["web_endpoint_id"])
    if candidate is None and keys["source_record_id"]:
        candidate = indexes["by_source_record"].get(keys["source_record_id"])
    if candidate is None and keys["normalized_url"]:
        candidate = indexes["by_url"].get(keys["normalized_url"])
    if candidate is None and keys["asset_identity_key"]:
        candidate = indexes["by_identity"].get(keys["asset_identity_key"])
    if candidate is None and keys["domain"] and keys["port"] is not None:
        candidate = indexes["by_domain_port"].get((keys["domain"], keys["port"]))
    if candidate is None and keys["host"] and keys["port"] is not None:
        candidate = indexes["by_host_port"].get((keys["host"], keys["port"]))
    if candidate is None and keys["ip"] and keys["port"] is not None:
        candidate = indexes["by_ip_port"].get((keys["ip"], keys["port"]))
    if candidate is None and keys["domain"]:
        candidate = indexes["by_domain"].get(keys["domain"])
    if candidate is None and keys["host"]:
        candidate = indexes["by_host"].get(keys["host"])
    if candidate is None and keys["ip"]:
        candidate = indexes["by_ip"].get(keys["ip"])
    return candidate


def _build_observation_asset_query(db: Session, observations: list[SourceObservation]):
    ids: set[str] = set()
    source_record_ids: set[str] = set()
    urls: set[str] = set()
    identity_keys: set[str] = set()
    domains: set[str] = set()
    hosts: set[str] = set()
    ips: set[str] = set()

    for obs in observations:
        keys = _observation_candidate_keys(obs)
        if keys["web_endpoint_id"]:
            ids.add(str(keys["web_endpoint_id"]))
        if keys["source_record_id"]:
            source_record_ids.add(str(keys["source_record_id"]))
        if keys["normalized_url"]:
            urls.add(str(keys["normalized_url"]))
        if keys["asset_identity_key"]:
            identity_keys.add(str(keys["asset_identity_key"]))
        if keys["domain"]:
            domains.add(str(keys["domain"]))
        if keys["host"]:
            hosts.add(str(keys["host"]))
        if keys["ip"]:
            ips.add(str(keys["ip"]))

    filters = []
    if ids:
        filters.append(WebEndpoint.id.in_(sorted(ids)))
    if urls:
        filters.append(WebEndpoint.normalized_url.in_(sorted(urls)))
    if domains:
        filters.append(WebEndpoint.domain.in_(sorted(domains)))
        filters.append(WebEndpoint.source_meta["domain"].astext.in_(sorted(domains)))
    if source_record_ids:
        filters.append(WebEndpoint.source_meta["source_record_id"].astext.in_(sorted(source_record_ids)))
    if identity_keys:
        filters.append(WebEndpoint.source_meta["asset_identity_key"].astext.in_(sorted(identity_keys)))
    if hosts:
        filters.append(WebEndpoint.source_meta["host"].astext.in_(sorted(hosts)))
        filters.append(WebEndpoint.source_meta["subdomain"].astext.in_(sorted(hosts)))
    if ips:
        filters.append(WebEndpoint.source_meta["ip"].astext.in_(sorted(ips)))

    query = db.query(WebEndpoint)
    if filters:
        return query.filter(or_(*filters))
    return query.filter(WebEndpoint.id.in_([]))


def _collect_result_assets(job_id: str, db: Session) -> list[WebEndpoint]:
    observations = (
        db.query(SourceObservation)
        .filter(SourceObservation.collect_job_id == job_id)
        .order_by(desc(SourceObservation.created_at))
        .all()
    )
    if not observations:
        return []

    assets = _build_observation_asset_query(db, observations).all()
    indexes = _build_result_lookup_indexes(assets)
    ordered_assets: list[WebEndpoint] = []
    seen: set[str] = set()

    for obs in observations:
        asset = _resolve_asset_from_observation(obs, indexes)
        if asset is None or asset.id in seen:
            continue
        seen.add(asset.id)
        ordered_assets.append(asset)

    return ordered_assets


def _has_valid_queries(queries: list[dict] | None) -> bool:
    if not isinstance(queries, list):
        return False
    return any(
        str((item or {}).get("source") or "").strip() and str((item or {}).get("query") or "").strip()
        for item in queries
    )


def _compute_log_state(job: CollectJob, content: str, exists: bool) -> str:
    if job.started_at is None:
        return "not_started"
    if not exists:
        if job.status == "running":
            return "running"
        return "log_not_found"
    if not content.strip():
        if job.status == "running":
            return "running"
        return "log_empty"
    if job.status == "running":
        return "running"
    return "finished" if job.finished_at else "log_ready"


def _build_job_result_preview_item(asset: WebEndpoint) -> dict:
    base = serialize_asset(asset)
    source_meta = getattr(asset, "source_meta", {}) or {}
    service = getattr(asset, "service", None)
    host_obj = getattr(service, "host", None) if service else getattr(asset, "host", None)
    return {
        "id": base["id"],
        "source": base.get("source"),
        "normalized_url": base["normalized_url"],
        "url": base["normalized_url"],
        "domain": getattr(asset, "domain", None) or source_meta.get("domain") or source_meta.get("host"),
        "ip": (getattr(host_obj, "ip", None) if host_obj else None) or source_meta.get("ip"),
        "port": (getattr(service, "port", None) if service else None) or source_meta.get("port"),
        "title": getattr(asset, "title", None),
        "status_code": getattr(asset, "status_code", None),
        "verified": base.get("verified"),
        "screenshot_status": base.get("screenshot_status"),
        "verify_error": base.get("verify_error"),
        "screenshot_error": base.get("screenshot_error"),
    }


def _build_job_result_preview_item_from_observation(obs: SourceObservation) -> dict:
    raw_payload = obs.raw_payload or {}
    normalized_url = (
        raw_payload.get("normalized_url")
        or raw_payload.get("fallback_url")
        or raw_payload.get("url")
        or raw_payload.get("resolved_domain")
        or raw_payload.get("resolved_host")
        or raw_payload.get("resolved_ip")
        or "unknown"
    )
    return {
        "id": getattr(obs, "id", None) or getattr(obs, "source_record_id", None) or raw_payload.get("source_record_id") or raw_payload.get("asset_identity_key") or normalized_url,
        "source": raw_payload.get("source") or getattr(obs, "source_name", None),
        "normalized_url": normalized_url,
        "url": raw_payload.get("url") or normalized_url,
        "domain": raw_payload.get("resolved_domain") or raw_payload.get("domain"),
        "ip": raw_payload.get("resolved_ip") or raw_payload.get("ip"),
        "port": raw_payload.get("resolved_port") or raw_payload.get("port"),
        "title": raw_payload.get("title"),
        "status_code": raw_payload.get("status_code"),
        "verified": None,
        "screenshot_status": None,
        "verify_error": raw_payload.get("verify_error"),
        "screenshot_error": raw_payload.get("screenshot_error"),
    }


def _collect_result_preview_items(job_id: str, db: Session) -> list[dict]:
    observations = (
        db.query(SourceObservation)
        .filter(SourceObservation.collect_job_id == job_id)
        .order_by(desc(SourceObservation.created_at))
        .all()
    )
    if not observations:
        return []

    assets = _build_observation_asset_query(db, observations).all()
    indexes = _build_result_lookup_indexes(assets)
    items: list[dict] = []
    seen_keys: set[str] = set()

    for obs in observations:
        asset = _resolve_asset_from_observation(obs, indexes)
        if asset is not None:
            dedup_key = f"asset:{asset.id}"
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            items.append(_build_job_result_preview_item(asset))
            continue

        fallback_item = _build_job_result_preview_item_from_observation(obs)
        dedup_key = f"obs:{fallback_item['id']}:{fallback_item['normalized_url']}"
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)
        items.append(fallback_item)

    return items


@router.get("/", response_model=List[CollectJobRead])
async def list_jobs(db: Session = Depends(get_db)):
    return db.query(CollectJob).order_by(desc(CollectJob.created_at)).all()


@router.get("/{job_id}", response_model=CollectJobDetail)
def get_collect_job(job_id: str, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    log_content, _exists = _get_log_content(job_id)

    detail = CollectJobDetail.model_validate(job)
    if job.started_at and job.finished_at:
        detail.duration = (job.finished_at - job.started_at).total_seconds()
    detail.command_line = construct_command_line(job)
    detail.task_details = _summarize_task_details(job, log_content, db)
    return detail


@router.get("/{job_id}/logs", response_model=JobLogResponse)
def get_job_logs(job_id: str, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    log_content, exists = _get_log_content(job_id)
    task_details = _summarize_task_details(job, log_content, db)
    return {
        "job_id": job_id,
        "log_state": _compute_log_state(job, log_content, exists),
        "content": log_content,
        "exists": exists,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "task_details": task_details,
    }


@router.get("/{job_id}/results", response_model=JobResultPreviewResponse)
def get_job_results(
    job_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    job = _get_job_or_404(db, job_id)
    log_content, _exists = _get_log_content(job_id)
    preview_items = _collect_result_preview_items(job_id, db)
    total = len(preview_items)
    task_details = _summarize_task_details(job, log_content, db, result_asset_count=total)
    items = preview_items[skip : skip + limit]
    return {
        "job_id": job_id,
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit,
        "task_details": task_details,
    }


@router.post("/preview")
async def preview_csv(file: UploadFile = File(...)):
    logger.info("Preview CSV start filename=%s", file.filename)
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="仅支持预览 .csv 文件")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="预览文件为空")

    import uuid

    safe_filename = f"preview_{uuid.uuid4().hex}.csv"
    target_path = UPLOAD_DIR / safe_filename
    target_path.write_bytes(content)

    try:
        preview_data = get_csv_preview(target_path)
        return {**preview_data, "file_path": str(target_path)}
    except Exception as exc:
        logger.exception("CSV preview failed path=%s", target_path)
        raise HTTPException(status_code=400, detail=f"CSV 预览失败: {exc}") from exc


@router.post("/collect")
def create_collect_job(payload: CollectJobCreate, db: Session = Depends(get_db)):
    logger.info("Create collect job: %s", payload.job_name)
    query_payload = {
        "queries": payload.queries,
        "time_window": payload.time_window,
        "source_type": payload.source_type,
    }
    if payload.file_path:
        query_payload["file_path"] = payload.file_path

    if "csv_import" not in payload.sources and not _has_valid_queries(payload.queries):
        raise HTTPException(status_code=400, detail="未提供有效查询条件")

    job = CollectJob(
        job_name=payload.job_name,
        sources=payload.sources,
        query_payload=query_payload,
        created_by=payload.created_by,
        dedup_strategy=payload.dedup_strategy,
        field_mapping=payload.field_mapping,
        auto_verify=payload.auto_verify,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    log_file = LOGS_DIR / f"{job.id}.log"
    log_file.write_text(
        f"{job.created_at.isoformat()} - INFO - Task created name={job.job_name} sources={job.sources}\n",
        encoding="utf-8",
    )

    if "sample" in payload.sources:
        result = import_sample_assets(db, job)
        return {"job_id": job.id, "status": job.status, **result}

    return {"job_id": job.id, "status": job.status}


@router.post("/{job_id}/rerun")
def rerun_job(job_id: str, db: Session = Depends(get_db)):
    original_job = _get_job_or_404(db, job_id)

    new_job_payload = CollectJobCreate(
        job_name=f"{original_job.job_name} (Rerun)",
        sources=original_job.sources,
        queries=(original_job.query_payload or {}).get("queries", []),
        file_path=(original_job.query_payload or {}).get("file_path"),
        source_type=(original_job.query_payload or {}).get("source_type"),
        created_by="rerun",
        dedup_strategy=original_job.dedup_strategy,
        field_mapping=original_job.field_mapping,
        auto_verify=original_job.auto_verify,
    )
    return create_collect_job(new_job_payload, db)


@router.post("/{job_id}/start")
def start_task(job_id: str, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    if job.status == "running":
        return {"message": "Job is already running", "job_id": job_id}

    job.status = "running"
    db.commit()

    from app.tasks.collect import run_collect_task

    run_in_process(run_collect_task, job_id, delay=1)
    return {"message": "Job started in background", "job_id": job_id}


@router.post("/{job_id}/stop")
def stop_task(job_id: str, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    job.status = "cancelled"
    db.commit()
    return {"message": "Job cancellation requested", "job_id": job_id}


@router.get("/{job_id}/status")
def get_task_status(job_id: str, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)

    return {
        "id": job.id,
        "status": job.status,
        "progress": job.progress,
        "success_count": job.success_count,
        "failed_count": job.failed_count,
        "duplicate_count": job.duplicate_count,
        "total_count": job.total_count,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "error_message": job.error_message,
    }
