from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import SavedSelection, SelectionItem
from app.schemas import SelectionCreateRequest

router = APIRouter()


@router.post("")
def create_selection(payload: SelectionCreateRequest, db: Session = Depends(get_db)):
    selection = SavedSelection(
        selection_name=payload.selection_name,
        selection_type=payload.selection_type,
        filter_snapshot=payload.filter_snapshot,
        created_by=payload.created_by,
    )
    db.add(selection)
    db.commit()
    db.refresh(selection)

    for asset_id in payload.asset_ids:
        db.add(SelectionItem(selection_id=selection.id, asset_id=asset_id))
    db.commit()
    return {"selection_id": selection.id}


@router.get("")
def list_selections(db: Session = Depends(get_db)):
    return db.query(SavedSelection).order_by(SavedSelection.created_at.desc()).all()
