from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import WebEndpoint

router = APIRouter()


@router.get("")
def list_assets(db: Session = Depends(get_db), domain: str | None = None, label_status: str | None = None):
    query = db.query(WebEndpoint)
    if domain:
        query = query.filter(WebEndpoint.domain == domain)
    if label_status:
        query = query.filter(WebEndpoint.label_status == label_status)
    return query.order_by(WebEndpoint.last_seen_at.desc().nullslast()).all()


@router.get("/{asset_id}")
def get_asset(asset_id: str, db: Session = Depends(get_db)):
    asset = db.get(WebEndpoint, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset
