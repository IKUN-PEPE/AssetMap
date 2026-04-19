from typing import List
import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.config import BASE_DIR
from app.core.db import get_db
from app.models import CollectJob
from app.schemas import CollectJobCreate, FofaCsvImportRequest, CollectJobRead
from app.services.collectors.fofa_csv import parse_fofa_csv
from app.services.collectors.hunter_csv import parse_hunter_csv
from app.services.collectors.import_service import SampleImportService
from app.services.collectors.preview import get_csv_preview
from app.tasks.sample_import import import_sample_assets

router = APIRouter()
logger = logging.getLogger(__name__)

UPLOAD_DIR = BASE_DIR / "tmp_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

@router.get("/", response_model=List[CollectJobRead])
async def list_jobs(db: Session = Depends(get_db)):
    """获取所有采集任务列表，按时间倒序"""
    return db.query(CollectJob).order_by(desc(CollectJob.created_at)).all()

@router.post("/preview")
async def preview_csv(
    file: UploadFile = File(...),
):
    """
    上传并预览 CSV 内容（前 10 行）
    """
    logger.info("Preview CSV start filename=%s", file.filename)
    if not file.filename or not file.filename.lower().endswith(".csv"):
        logger.warning("Rejected preview because file is not csv: %s", file.filename)
        raise HTTPException(status_code=400, detail="仅支持预览 .csv 文件")

    content = await file.read()
    if not content:
        logger.warning("Rejected preview because file is empty: %s", file.filename)
        raise HTTPException(status_code=400, detail="预览文件为空")

    # 使用安全的随机文件名避免路径穿越
    import uuid
    safe_filename = f"preview_{uuid.uuid4().hex}.csv"
    target_path = UPLOAD_DIR / safe_filename
    target_path.write_bytes(content)
    logger.info("Saved preview CSV safe_path=%s size=%s", target_path, len(content))

    try:
        preview_data = get_csv_preview(target_path)
        return {
            **preview_data,
            "file_path": str(target_path)
        }
    except Exception as exc:
        logger.exception("CSV preview failed path=%s", target_path)
        raise HTTPException(status_code=400, detail=f"CSV 预览失败: {exc}")


@router.post("/collect")
def create_collect_job(payload: CollectJobCreate, db: Session = Depends(get_db)):
    logger.info("Create collect job: %s", payload.job_name)
    query_payload = {
        "queries": payload.queries, 
        "time_window": payload.time_window
    }
    if payload.file_path:
        query_payload["file_path"] = payload.file_path

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

    if any(source == "sample" for source in payload.sources):
        logger.info("Running sample import for job=%s", job.id)
        result = import_sample_assets(db, job)
        logger.info("Sample import success job=%s imported=%s", job.id, result.get("imported"))
        return {"job_id": job.id, "status": job.status, **result}

    return {"job_id": job.id, "status": job.status}


@router.post("/{job_id}/start")
def start_task(job_id: str, db: Session = Depends(get_db)):
    """
    将任务状态置为 pending 并触发 run_collect_task
    """
    job = db.get(CollectJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status == "running":
        return {"message": "Job is already running", "job_id": job_id}

    job.status = "pending"
    db.commit()

    from app.tasks.collect import run_collect_task
    run_collect_task.schedule(args=(job_id,), delay=1)

    return {"message": "Job started in background", "job_id": job_id}


@router.post("/{job_id}/stop")
def stop_task(job_id: str, db: Session = Depends(get_db)):
    """
    将任务状态置为 cancelled
    """
    job = db.get(CollectJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job.status = "cancelled"
    db.commit()

    return {"message": "Job cancellation requested", "job_id": job_id}


@router.get("/{job_id}/status")
def get_task_status(job_id: str, db: Session = Depends(get_db)):
    """
    返回最新的任务统计和进度
    """
    job = db.get(CollectJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

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
        "error_message": job.error_message
    }

@router.get("/{job_id}", response_model=CollectJobRead)
def get_collect_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(CollectJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.post("/import-fofa-csv")
def import_fofa_csv(payload: FofaCsvImportRequest, db: Session = Depends(get_db)):
    logger.info("Import FOFA CSV by path: %s", payload.file_path)
    job = CollectJob(
        job_name=payload.job_name,
        sources=["fofa_csv"],
        query_payload={"file_path": payload.file_path},
        created_by=payload.created_by,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        records = parse_fofa_csv(payload.file_path)
        logger.info("Parsed FOFA CSV rows=%s file=%s", len(records), payload.file_path)
        result = SampleImportService().import_records(db, job, records)
        logger.info("FOFA CSV import success job=%s imported=%s", job.id, result.get("imported"))
        return {"job_id": job.id, "status": job.status, **result}
    except Exception as exc:
        logger.exception("FOFA CSV import failed job=%s file=%s", job.id, payload.file_path)
        raise HTTPException(status_code=400, detail=f"FOFA CSV 导入失败: {exc}")


@router.post("/upload-fofa-csv")
async def upload_fofa_csv(
    job_name: str = Form(...),
    created_by: str = Form("system"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    logger.info("Upload FOFA CSV start filename=%s", file.filename)
    if not file.filename or not file.filename.lower().endswith(".csv"):
        logger.warning("Rejected upload because file is not csv: %s", file.filename)
        raise HTTPException(status_code=400, detail="仅支持上传 .csv 文件")

    content = await file.read()
    if not content:
        logger.warning("Rejected upload because file is empty: %s", file.filename)
        raise HTTPException(status_code=400, detail="上传文件为空")

    target_path = UPLOAD_DIR / file.filename
    target_path.write_bytes(content)
    logger.info("Saved uploaded FOFA CSV path=%s size=%s", target_path, len(content))

    job = CollectJob(
        job_name=job_name,
        sources=["fofa_csv"],
        query_payload={"file_path": str(target_path)},
        created_by=created_by,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        records = parse_fofa_csv(target_path)
        logger.info("Parsed uploaded FOFA CSV rows=%s path=%s", len(records), target_path)
        result = SampleImportService().import_records(db, job, records)
        logger.info("Uploaded FOFA CSV import success job=%s imported=%s", job.id, result.get("imported"))
        return {"job_id": job.id, "status": job.status, **result}
    except Exception as exc:
        logger.exception("Uploaded FOFA CSV import failed job=%s path=%s", job.id, target_path)
        raise HTTPException(status_code=400, detail=f"FOFA CSV 上传导入失败: {exc}")


@router.post("/upload-hunter-csv")
async def upload_hunter_csv(
    job_name: str = Form(...),
    created_by: str = Form("system"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    logger.info("Upload Hunter CSV start filename=%s", file.filename)
    if not file.filename or not file.filename.lower().endswith(".csv"):
        logger.warning("Rejected upload because file is not csv: %s", file.filename)
        raise HTTPException(status_code=400, detail="仅支持上传 .csv 文件")

    content = await file.read()
    if not content:
        logger.warning("Rejected upload because file is empty: %s", file.filename)
        raise HTTPException(status_code=400, detail="上传文件为空")

    target_path = UPLOAD_DIR / file.filename
    target_path.write_bytes(content)
    logger.info("Saved uploaded Hunter CSV path=%s size=%s", target_path, len(content))

    job = CollectJob(
        job_name=job_name,
        sources=["hunter_csv"],
        query_payload={"file_path": str(target_path)},
        created_by=created_by,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        records = parse_hunter_csv(target_path)
        logger.info("Parsed uploaded Hunter CSV rows=%s path=%s", len(records), target_path)
        result = SampleImportService().import_records(db, job, records)
        logger.info("Uploaded Hunter CSV import success job=%s imported=%s", job.id, result.get("imported"))
        return {"job_id": job.id, "status": job.status, **result}
    except Exception as exc:
        logger.exception("Uploaded Hunter CSV import failed job=%s path=%s", job.id, target_path)
        raise HTTPException(status_code=400, detail=f"Hunter CSV 上传导入失败: {exc}")
