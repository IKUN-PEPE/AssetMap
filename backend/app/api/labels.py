from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Label, LabelAuditLog, WebEndpoint
from app.schemas import LabelBatchRequest

router = APIRouter()


@router.post("/batch")
def batch_labels(payload: LabelBatchRequest, db: Session = Depends(get_db)):
    batch_id = str(uuid4())
    for asset_id in payload.asset_ids:
        asset = db.get(WebEndpoint, asset_id)
        if not asset:
            continue
        before_label = {"label_status": asset.label_status}
        asset.label_status = payload.label_type
        label = Label(
            asset_id=asset_id,
            label_type=payload.label_type,
            reason=payload.reason,
            created_by=payload.created_by,
        )
        audit = LabelAuditLog(
            batch_id=batch_id,
            asset_id=asset_id,
            asset_type="web_endpoint",
            before_label=before_label,
            after_label={"label_status": payload.label_type},
            action_type="create",
            operator=payload.created_by,
        )
        db.add(label)
        db.add(audit)
    db.commit()
    return {"batch_id": batch_id, "applied_count": len(payload.asset_ids)}
