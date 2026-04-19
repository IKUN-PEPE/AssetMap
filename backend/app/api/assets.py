import asyncio
import logging
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from playwright.async_api import async_playwright
from pydantic import BaseModel
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, selectinload

from urllib.parse import quote

from app.core.config import settings
from app.core.db import SessionLocal, get_db
from app.models import Host, Service, WebEndpoint
from app.models.support import Label, LabelAuditLog, Screenshot, SelectionItem, SourceObservation
from app.services.screenshot.service import build_output_filename, run_screenshot_job

router = APIRouter()
logger = logging.getLogger(__name__)
SCREENSHOT_DIR = Path(settings.screenshot_output_dir).resolve()
VERIFY_TASKS: dict[str, SimpleNamespace] = {}


class VerifyBatchRequest(BaseModel):
    asset_ids: list[str]
    verified: bool = True


async def fetch_status_code_with_playwright(context, url: str) -> int | None:
    page = await context.new_page()
    try:
        response = await page.goto(url, wait_until="commit", timeout=8000)
        return response.status if response else None
    except Exception as exc:
        logger.debug("Fetch status code failed for %s: %s", url, exc)
        return None
    finally:
        await page.close()


async def capture_asset_screenshot_async(asset: WebEndpoint) -> str:
    output_dir = Path(settings.screenshot_output_dir)
    result_csv = Path(settings.result_output_dir) / "assetmap_results.csv"
    summary_txt = Path(settings.result_output_dir) / "assetmap_summary.txt"

    await run_screenshot_job(
        asset_rows=[
            {
                "seq": asset.id,
                "host": asset.domain or asset.normalized_url,
                "title": asset.title or "未命名",
                "url": asset.normalized_url,
            }
        ],
        output_dir=output_dir,
        result_csv=result_csv,
        summary_txt=summary_txt,
        skip_existing=False,
    )

    file_name = build_output_filename(asset.id, asset.title or "未命名", asset.normalized_url)
    return str(output_dir / file_name)


def build_public_screenshot_url(path: Path) -> str | None:
    try:
        relative_path = path.resolve().relative_to(SCREENSHOT_DIR)
    except ValueError:
        return None
    encoded_path = quote(PurePosixPath(relative_path.as_posix()).as_posix(), safe="/")
    return f"/static/screenshots/{encoded_path}"


def serialize_verify_task(task: SimpleNamespace) -> dict:
    return {
        "task_id": task.task_id,
        "task_type": task.task_type,
        "status": task.status,
        "total": task.total,
        "processed": task.processed,
        "success": task.success,
        "failed": task.failed,
        "message": task.message,
        "cancel_requested": task.cancel_requested,
    }


async def process_one_asset(
    asset_id: str,
    asset_url: str,
    verified: bool,
    context,
    task: SimpleNamespace,
    semaphore: asyncio.Semaphore
):
    async with semaphore:
        if task.cancel_requested:
            return

        db = SessionLocal()
        try:
            asset = db.get(WebEndpoint, asset_id)
            if not asset:
                return

            asset.verified = verified
            status_code = await fetch_status_code_with_playwright(context, asset_url)

            if status_code is None:
                task.failed += 1
                asset.status_code = None
            else:
                asset.status_code = status_code
                task.success += 1

            try:
                screenshot_path = await capture_asset_screenshot_async(asset)
                asset.screenshot_status = "success"
                db.query(Screenshot).filter(Screenshot.web_endpoint_id == asset.id).delete(synchronize_session=False)
                db.add(
                    Screenshot(
                        web_endpoint_id=asset.id,
                        file_name=Path(screenshot_path).name,
                        object_path=screenshot_path,
                        status="success",
                    )
                )
            except Exception:
                asset.screenshot_status = "failed"
                logger.warning("Capture screenshot failed url=%s asset_id=%s", asset_url, asset.id, exc_info=True)

            db.commit()
            task.processed += 1
            task.message = f"正在验证并截图 {task.processed} / {task.total}"

            if task.cancel_requested:
                task.status = "cancelled"
                task.message = f"已取消，已处理 {task.processed} / {task.total}"


        except Exception:
            db.rollback()
            logger.warning("Process single asset failed asset_id=%s", asset_id, exc_info=True)
            task.failed += 1
            task.processed += 1
        finally:
            db.close()


async def start_verify_task_async(task: SimpleNamespace, asset_ids: list[str], verified: bool, assets_data: list[tuple[str, str]]):
    task.status = "running"

    semaphore = asyncio.Semaphore(5)  # 限制为并发 5 个浏览器页面处理

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(ignore_https_errors=True)
            try:
                process_tasks = []
                for asset_id, url in assets_data:
                    process_tasks.append(
                        process_one_asset(asset_id, url, verified, context, task, semaphore)
                    )

                await asyncio.gather(*process_tasks)

                if task.status != "cancelled":
                    task.status = "completed"
                    task.message = "验证并截图完成"
            finally:
                await context.close()
                await browser.close()
    except Exception:
        task.status = "failed"
        task.message = "验证失败"
        logger.warning("Verify task failed task_id=%s", task.task_id, exc_info=True)


def serialize_asset(asset: WebEndpoint) -> dict:
    source_meta = asset.source_meta or {}
    screenshot_url = None
    if asset.screenshots:
        sorted_shots = sorted(
            asset.screenshots,
            key=lambda item: item.captured_at or 0,
            reverse=True,
        )
        for shot in sorted_shots:
            if not shot.object_path:
                continue
            path = Path(shot.object_path).resolve()
            if not path.exists():
                continue
            screenshot_url = build_public_screenshot_url(path)
            if screenshot_url is not None:
                break

    # 回退逻辑：如果数据库没有记录或文件不存在，尝试按前缀匹配磁盘文件 (兼容旧数据)
    if screenshot_url is None:
        prefix = asset.id[:20]
        try:
            for p in SCREENSHOT_DIR.glob(f"{prefix}*.png"):
                screenshot_url = build_public_screenshot_url(p)
                if screenshot_url:
                    break
        except Exception:
            pass

    return {
        "id": asset.id,
        "normalized_url": asset.normalized_url,
        "title": asset.title,
        "status_code": asset.status_code,
        "screenshot_status": asset.screenshot_status,
        "label_status": asset.label_status,
        "verified": asset.verified,
        "source": source_meta.get("source"),
        "first_seen_at": asset.first_seen_at.isoformat() if asset.first_seen_at else None,
        "last_seen_at": asset.last_seen_at.isoformat() if asset.last_seen_at else None,
        "screenshot_url": screenshot_url,
        "has_screenshot": screenshot_url is not None,
    }


@router.get("")
def list_assets(
    db: Session = Depends(get_db),
    domain: str | None = None,
    label_status: str | None = None,
    screenshot_status: str | None = None,
    has_screenshot: bool | None = None,
    source: str | None = None,
    q: str | None = None,
):
    query = db.query(WebEndpoint).options(selectinload(WebEndpoint.screenshots))
    if domain:
        query = query.filter(WebEndpoint.domain == domain)
    if label_status:
        query = query.filter(WebEndpoint.label_status == label_status)
    if screenshot_status:
        query = query.filter(WebEndpoint.screenshot_status == screenshot_status)
    if has_screenshot is not None:
        if has_screenshot:
            query = query.filter(WebEndpoint.screenshots.any())
        else:
            query = query.filter(~WebEndpoint.screenshots.any())
    if source:
        query = query.filter(WebEndpoint.source_meta["source"].astext == source)
    if q:
        like_value = f"%{q}%"
        query = query.filter(
            or_(
                WebEndpoint.normalized_url.ilike(like_value),
                WebEndpoint.domain.ilike(like_value),
                WebEndpoint.title.ilike(like_value),
            )
        )

    return [serialize_asset(asset) for asset in query.order_by(WebEndpoint.last_seen_at.desc().nullslast()).all()]


@router.get("/{asset_id}")
def get_asset(asset_id: str, db: Session = Depends(get_db)):
    asset = db.get(WebEndpoint, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return serialize_asset(asset)


@router.get("/verify-batch/{task_id}")
def get_verify_task(task_id: str):
    task = VERIFY_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return serialize_verify_task(task)


@router.post("/verify-batch")
def verify_assets(payload: VerifyBatchRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    assets = db.query(WebEndpoint).filter(WebEndpoint.id.in_(payload.asset_ids)).all()
    # Cache ID and URL to pass into async task without keeping objects attached to main session
    assets_data = [(a.id, a.normalized_url) for a in assets]

    task = SimpleNamespace(
        task_id=str(uuid4()),
        task_type="asset_verify",
        status="pending",
        total=len(assets),
        processed=0,
        success=0,
        failed=0,
        message=f"正在验证 0 / {len(assets)}",
        cancel_requested=False,
    )

    VERIFY_TASKS[task.task_id] = task

    # Fire and forget async task via BackgroundTasks
    background_tasks.add_task(start_verify_task_async, task, payload.asset_ids, payload.verified, assets_data)

    return {"task_id": task.task_id, "status": task.status}


@router.post("/verify-batch/{task_id}/cancel")
def cancel_verify_task(task_id: str):
    task = VERIFY_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status in {"completed", "failed", "cancelled"}:
        return serialize_verify_task(task)

    task.cancel_requested = True
    task.status = "cancelled"
    task.message = f"已取消，已处理 {task.processed} / {task.total}"
    return serialize_verify_task(task)


@router.delete("/{asset_id}")
def delete_asset(asset_id: str, db: Session = Depends(get_db)):
    asset = db.get(WebEndpoint, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    source_meta = asset.source_meta or {}
    source = source_meta.get("source")
    port = asset.service.port if asset.service else None
    host = db.get(Host, asset.host_id) if asset.host_id else None
    service = db.get(Service, asset.service_id) if asset.service_id else None

    # 同步删除物理截图文件
    screenshots = db.query(Screenshot).filter(Screenshot.web_endpoint_id == asset.id).all()
    for shot in screenshots:
        if shot.object_path:
            p = Path(shot.object_path)
            try:
                if p.exists():
                    p.unlink()
                    logger.info("Physical screenshot file deleted: %s", p)
            except Exception as e:
                logger.error("Failed to delete physical file %s: %s", p, e)

    db.query(Screenshot).filter(Screenshot.web_endpoint_id == asset.id).delete(synchronize_session=False)
    db.query(Label).filter(and_(Label.asset_type == "web_endpoint", Label.asset_id == asset.id)).delete(synchronize_session=False)
    db.query(LabelAuditLog).filter(and_(LabelAuditLog.asset_type == "web_endpoint", LabelAuditLog.asset_id == asset.id)).delete(synchronize_session=False)
    db.query(SelectionItem).filter(and_(SelectionItem.asset_type == "web_endpoint", SelectionItem.asset_id == asset.id)).delete(synchronize_session=False)

    source_obs_query = db.query(SourceObservation).filter(SourceObservation.source_name == source) if source else db.query(SourceObservation)
    source_obs_query = source_obs_query.filter(
        or_(
            SourceObservation.raw_payload["url"].astext == asset.normalized_url,
            and_(
                SourceObservation.raw_payload["ip"].astext == (host.ip if host else None),
                SourceObservation.raw_payload["port"].astext == (str(port) if port is not None else None),
            ),
        )
    )
    source_obs_query.delete(synchronize_session=False)

    db.delete(asset)
    db.flush()

    if service:
        remaining_endpoints = db.query(WebEndpoint).filter(WebEndpoint.service_id == service.id).count()
        if remaining_endpoints == 0:
            db.delete(service)
            db.flush()

    if host:
        remaining_services = db.query(Service).filter(Service.host_id == host.id).count()
        if remaining_services == 0:
            db.delete(host)

    db.commit()
    return {"deleted": True, "asset_id": asset_id}


