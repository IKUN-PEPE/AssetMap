from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import CollectJob
from app.schemas import CollectJobCreate
from app.tasks.sample_import import import_sample_assets

router = APIRouter()


@router.post("/collect")
def create_collect_job(payload: CollectJobCreate, db: Session = Depends(get_db)):
    job = CollectJob(
        job_name=payload.job_name,
        sources=payload.sources,
        query_payload={"queries": payload.queries, "time_window": payload.time_window},
        created_by=payload.created_by,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    if any(source == "sample" for source in payload.sources):
        result = import_sample_assets(db, job)
        return {"job_id": job.id, "status": job.status, **result}

    return {"job_id": job.id, "status": job.status}


@router.get("/{job_id}")
def get_collect_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(CollectJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
