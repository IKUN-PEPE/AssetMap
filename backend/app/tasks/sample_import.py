import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import CollectJob
from app.services.collectors.import_service import SampleImportService


def import_sample_assets(db: Session, job: CollectJob, sample_path: str | None = None) -> dict[str, int]:
    path = Path(sample_path or settings.sample_data_path)
    records = json.loads(path.read_text(encoding="utf-8"))
    service = SampleImportService()
    return service.import_records(db, job, records)
