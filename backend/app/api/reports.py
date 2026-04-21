from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Report
from app.schemas import ReportCreateRequest
from app.schemas.common import ReportRead

router = APIRouter()


@router.get("/", response_model=List[ReportRead])
def get_reports(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    reports = db.query(Report).order_by(Report.created_at.desc()).offset(skip).limit(limit).all()
    return reports


@router.get("/{report_id}", response_model=ReportRead)
def get_report(report_id: str, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.post("", response_model=ReportRead)
def create_report(payload: ReportCreateRequest, db: Session = Depends(get_db)):
    report = Report(
        report_name=payload.report_name,
        report_type=payload.report_formats[0] if payload.report_formats else "html",
        scope_type=payload.scope_type,
        scope_payload={
            "selection_id": payload.selection_id,
            "asset_ids": payload.asset_ids,
            "exclude_false_positive": payload.exclude_false_positive,
            "exclude_confirmed": payload.exclude_confirmed,
        },
        created_by=payload.created_by,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@router.delete("/{report_id}", status_code=204)
def delete_report(report_id: str, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    db.delete(report)
    db.commit()
    return


@router.post("/{report_id}/regenerate", response_model=ReportRead)
def regenerate_report(report_id: str, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    
    # Reset status for regeneration
    report.status = "pending"
    report.finished_at = None
    report.error_message = None
    # Here you would typically trigger a background task
    # For example: from app.tasks import generate_report_task; generate_report_task.delay(report.id)
    
    db.commit()
    db.refresh(report)
    return report
