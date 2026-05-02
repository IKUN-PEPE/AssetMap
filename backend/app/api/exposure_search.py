from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.models.exposure_search import ExposureSearchTask, ExposureSearchResult
from app.schemas.exposure_search import (
    ExposureSearchTaskCreate,
    ExposureSearchTaskSchema,
    ExposureSearchResultSchema,
    BatchUpdateExposureResults,
    ConfirmImportExposureResults
)
from app.services.exposure_search import ExposureSearchService
from app.tasks.collect_persistence import save_assets
import asyncio
import logging
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/tasks", response_model=ExposureSearchTaskSchema)
async def create_task(
    payload: ExposureSearchTaskCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    task = ExposureSearchTask(
        name=payload.name,
        org_keywords=payload.org_keywords,
        title_keywords=payload.title_keywords,
        url_keywords=payload.url_keywords,
        file_types=payload.file_types,
        sources=payload.sources,
        status="pending"
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    if payload.auto_run:
        service = ExposureSearchService(db)
        background_tasks.add_task(service.run_task, task.id)

    return task

@router.get("/tasks", response_model=list[ExposureSearchTaskSchema])
def list_tasks(db: Session = Depends(get_db)):
    return db.query(ExposureSearchTask).order_by(ExposureSearchTask.created_at.desc()).all()

@router.get("/tasks/{task_id}", response_model=ExposureSearchTaskSchema)
def get_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(ExposureSearchTask).filter(ExposureSearchTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@router.get("/tasks/{task_id}/results", response_model=list[ExposureSearchResultSchema])
def list_results(
    task_id: str,
    status: str | None = None,
    db: Session = Depends(get_db)
):
    query = db.query(ExposureSearchResult).filter(ExposureSearchResult.task_id == task_id)
    if status:
        query = query.filter(ExposureSearchResult.status == status)
    return query.order_by(ExposureSearchResult.created_at.desc()).all()

@router.post("/results/batch-update")
def batch_update_results(payload: BatchUpdateExposureResults, db: Session = Depends(get_db)):
    results = db.query(ExposureSearchResult).filter(ExposureSearchResult.id.in_(payload.ids)).all()
    for res in results:
        res.status = payload.status
    db.commit()
    return {"message": f"Updated {len(results)} results"}

@router.post("/tasks/{task_id}/confirm-import")
async def confirm_import(
    task_id: str,
    payload: ConfirmImportExposureResults,
    db: Session = Depends(get_db)
):
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
    clue_count = 0
    for res in results:
        is_web_asset = False
        if res.url.startswith("http"):
            # Refined filter for web assets vs clues
            if res.file_type in ["pdf", "doc", "docx", "xls", "xlsx", "sql"] or "github.com" in res.url or "pan.baidu.com" in res.url:
                is_web_asset = False
            else:
                is_web_asset = True

        if is_web_asset:
            web_records.append({
                "url": res.url,
                "title": res.title,
                "source": f"exposure_search:{res.source}",
                "raw_payload": res.raw_payload
            })
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
            
            save_assets(db, import_job, web_records, "exposure_search")
        except Exception as e:
            logger.error(f"Failed to import assets: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Asset import failed: {str(e)}")

    db.commit()
    return {
        "message": f"Processed {len(results)} results: {len(web_records)} imported as assets, {clue_count} marked as valid clues."
    }

@router.delete("/tasks/{task_id}")
def delete_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(ExposureSearchTask).filter(ExposureSearchTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()
    return {"message": "Task deleted"}
