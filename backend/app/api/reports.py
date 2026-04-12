from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Report
from app.schemas import ReportCreateRequest

router = APIRouter()


@router.post("")
def create_report(payload: ReportCreateRequest, db: Session = Depends(get_db)):
    report = Report(
        report_name=payload.report_name,
        report_type=payload.report_formats[0],
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
    return {"report_id": report.id, "status": report.status}
