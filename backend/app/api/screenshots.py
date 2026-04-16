import asyncio
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal, get_db
from app.models import Screenshot, WebEndpoint
from app.schemas import ScreenshotBatchRequest
from app.services.screenshot.service import build_output_filename, run_screenshot_job

router = APIRouter()
SCREENSHOT_TASKS: dict[str, SimpleNamespace] = {}


def serialize_screenshot_task(task: SimpleNamespace) -> dict:
    return {
        'task_id': task.task_id,
        'task_type': task.task_type,
        'status': task.status,
        'total': task.total,
        'processed': task.processed,
        'success': task.success,
        'failed': task.failed,
        'message': task.message,
    }


def start_screenshot_task(task: SimpleNamespace, asset_ids: list[str], skip_existing: bool):
    def run():
        db = SessionLocal()
        try:
            assets = db.query(WebEndpoint).filter(WebEndpoint.id.in_(asset_ids)).all()
            task.status = 'running'
            task.total = len(assets)
            task.message = f'正在截图 0 / {len(assets)}'
            output_dir = Path(settings.screenshot_output_dir)
            result_csv = Path(settings.result_output_dir) / 'assetmap_results.csv'
            summary_txt = Path(settings.result_output_dir) / 'assetmap_summary.txt'

            for index, asset in enumerate(assets, start=1):
                if task.cancel_requested:
                    task.status = 'cancelled'
                    task.message = f'已取消，已处理 {task.processed} / {task.total}'
                    break

                asset_rows = [{
                    'seq': asset.id,
                    'host': asset.domain or asset.normalized_url,
                    'title': asset.title or '未命名',
                    'url': asset.normalized_url,
                }]
                result = asyncio.run(
                    run_screenshot_job(
                        asset_rows=asset_rows,
                        output_dir=output_dir,
                        result_csv=result_csv,
                        summary_txt=summary_txt,
                        skip_existing=skip_existing,
                    )
                )
                actual_path = None
                if isinstance(result, dict):
                    rows = result.get('results') or []
                    if rows and isinstance(rows, list):
                        first_row = rows[0]
                        if isinstance(first_row, dict):
                            actual_path = first_row.get('screenshot_path')

                if not actual_path:
                    file_name = build_output_filename(asset.id, asset.title or '未命名', asset.normalized_url)
                    actual_path = str(output_dir / file_name)

                asset.screenshot_status = 'success'
                db.query(Screenshot).filter(Screenshot.web_endpoint_id == asset.id).delete(synchronize_session=False)
                db.add(
                    Screenshot(
                        web_endpoint_id=asset.id,
                        file_name=Path(actual_path).name,
                        object_path=str(actual_path),
                        status='success',
                    )
                )
                task.processed = index
                task.success += 1
                task.message = f'正在截图 {task.processed} / {task.total}'

            if task.status != 'cancelled':
                task.status = 'completed'
                task.message = '截图完成'
            db.commit()
        except Exception:
            db.rollback()
            task.status = 'failed'
            task.message = '截图失败'
        finally:
            db.close()

    Thread(target=run, daemon=True).start()


@router.get('/batch/{task_id}')
def get_screenshot_task(task_id: str):
    task = SCREENSHOT_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail='Task not found')
    return serialize_screenshot_task(task)


@router.post('/batch')
def batch_screenshots(payload: ScreenshotBatchRequest, db: Session = Depends(get_db)):
    assets = db.query(WebEndpoint).filter(WebEndpoint.id.in_(payload.asset_ids)).all()
    if not assets:
        raise HTTPException(status_code=404, detail='No assets found')

    task = SimpleNamespace(
        task_id=str(uuid4()),
        task_type='asset_screenshot',
        status='pending',
        total=len(assets),
        processed=0,
        success=0,
        failed=0,
        message=f'正在截图 0 / {len(assets)}',
        cancel_requested=False,
    )
    SCREENSHOT_TASKS[task.task_id] = task
    start_screenshot_task(task, payload.asset_ids, payload.skip_existing)
    return {'task_id': task.task_id, 'status': task.status}


@router.post('/recover')
def recover_screenshots(payload: ScreenshotBatchRequest, db: Session = Depends(get_db)):
    assets = db.query(WebEndpoint).filter(WebEndpoint.id.in_(payload.asset_ids)).all()
    if not assets:
        raise HTTPException(status_code=404, detail='No assets found')

    task = SimpleNamespace(
        task_id=str(uuid4()),
        task_type='asset_screenshot',
        status='pending',
        total=len(assets),
        processed=0,
        success=0,
        failed=0,
        message=f'正在补截图 0 / {len(assets)}',
        cancel_requested=False,
    )
    SCREENSHOT_TASKS[task.task_id] = task
    start_screenshot_task(task, payload.asset_ids, False)
    return {'task_id': task.task_id, 'status': task.status}


@router.post('/batch/{task_id}/cancel')
def cancel_screenshot_task(task_id: str):
    task = SCREENSHOT_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail='Task not found')
    if task.status in {'completed', 'failed', 'cancelled'}:
        return serialize_screenshot_task(task)

    task.cancel_requested = True
    task.status = 'cancelled'
    task.message = f'已取消，已处理 {task.processed} / {task.total}'
    return serialize_screenshot_task(task)
