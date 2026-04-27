from __future__ import annotations

import re
from datetime import datetime, timezone
from mimetypes import guess_type
from pathlib import Path
from typing import List
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.models import Report
from app.schemas import ReportCreateRequest
from app.schemas.common import ReportRead

router = APIRouter()
_REPORTS_SCHEMA_CHECKED_ENGINES: set[str] = set()


def _reports_dir() -> Path:
    return Path(settings.result_output_dir).resolve()


def _safe_file_name(name: str, fallback_stem: str, suffix: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]+", "_", name or "").strip()
    cleaned = cleaned or fallback_stem
    cleaned = Path(cleaned).name
    if suffix and not cleaned.lower().endswith(f".{suffix.lower()}"):
        cleaned = f"{cleaned}.{suffix}"
    return cleaned


def _default_report_file_name(report: Report) -> str:
    suffix = (report.report_type or "txt").lstrip(".")
    safe_name = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", report.report_name).strip("_") or "report"
    return f"{report.id}_{safe_name}.{suffix}"


def _report_path(report: Report) -> Path | None:
    if not report.object_path:
        return None
    return Path(report.object_path)


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ensure_reports_schema_columns(db: Session) -> None:
    bind = getattr(db, "bind", None)
    if bind is None:
        return

    engine_key = str(getattr(bind, "url", ""))
    if engine_key in _REPORTS_SCHEMA_CHECKED_ENGINES:
        return

    inspector = inspect(bind)
    try:
        tables = set(inspector.get_table_names())
    except Exception:
        return
    if "reports" not in tables:
        _REPORTS_SCHEMA_CHECKED_ENGINES.add(engine_key)
        return

    columns = {item["name"] for item in inspector.get_columns("reports")}
    statements: list[str] = []
    if "file_size" not in columns:
        statements.append("ALTER TABLE reports ADD COLUMN file_size INTEGER")
    if "error_message" not in columns:
        statements.append("ALTER TABLE reports ADD COLUMN error_message TEXT")

    if statements:
        for statement in statements:
            db.execute(text(statement))
        db.commit()

    _REPORTS_SCHEMA_CHECKED_ENGINES.add(engine_key)


def _write_report_file(report: Report, report_content: str, file_name_hint: str | None) -> None:
    reports_dir = _reports_dir()
    reports_dir.mkdir(parents=True, exist_ok=True)
    file_name = _safe_file_name(
        file_name_hint or _default_report_file_name(report),
        fallback_stem=report.report_name,
        suffix=(report.report_type or "txt").lstrip("."),
    )
    stem = Path(file_name).stem
    suffix = Path(file_name).suffix
    unique_file_name = f"{stem}_{report.id}{suffix}"
    report_bytes = report_content.encode("utf-8")
    object_path = reports_dir / unique_file_name
    object_path.write_bytes(report_bytes)
    report.object_path = str(object_path)
    report.file_size = len(report_bytes)
    report.status = "completed"
    report.finished_at = _utcnow_naive()
    report.error_message = None


def _mark_report_failed(report: Report, error_message: str, *, clear_file: bool) -> None:
    if clear_file:
        report.object_path = None
        report.file_size = None
    report.status = "failed"
    report.finished_at = _utcnow_naive()
    report.error_message = error_message


def _resolve_report_content(
    report: Report,
    payload: ReportCreateRequest | None = None,
    *,
    allow_file_fallback: bool = False,
) -> str | None:
    if payload is not None and payload.report_content is not None:
        return payload.report_content
    scope_payload = getattr(report, "scope_payload", {}) or {}
    content = scope_payload.get("report_content")
    if content is None:
        if allow_file_fallback:
            path = _report_path(report)
            if path is not None and path.exists():
                try:
                    return path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    return None
        return None
    return str(content)


def _normalize_report_status(status: str | None) -> str:
    normalized = (status or "").strip().lower()
    mapping = {
        "generating": "running",
        "processing": "running",
        "in_progress": "running",
        "queued": "pending",
        "created": "pending",
        "done": "completed",
        "success": "completed",
        "error": "failed",
    }
    return mapping.get(normalized, normalized or "pending")


def _serialize_report(report: Report) -> dict:
    path = _report_path(report)
    file_size = getattr(report, "file_size", None)
    file_missing = False
    status = _normalize_report_status(getattr(report, "status", None))

    if path is not None:
        file_missing = not path.exists()
        if file_missing:
            status = "file_missing"
        elif file_size is None:
            try:
                file_size = path.stat().st_size
            except OSError:
                file_missing = True
                status = "file_missing"

    return {
        "id": report.id,
        "report_name": report.report_name,
        "status": status,
        "report_type": getattr(report, "report_type", None),
        "object_path": report.object_path,
        "file_size": file_size,
        "file_missing": file_missing,
        "download_url": f"/api/v1/reports/{report.id}/download" if path is not None else None,
        "created_at": report.created_at,
        "finished_at": report.finished_at,
        "total_assets": report.total_assets,
        "excluded_assets": report.excluded_assets,
        "error_message": getattr(report, "error_message", None),
    }


def _list_reports(db: Session, skip: int, limit: int) -> list[dict]:
    reports = db.query(Report).order_by(Report.created_at.desc()).offset(skip).limit(limit).all()
    return [_serialize_report(report) for report in reports]


@router.get("", response_model=List[ReportRead])
@router.get("/", response_model=List[ReportRead])
def get_reports(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    ensure_reports_schema_columns(db)
    return _list_reports(db, skip, limit)


@router.get("/{report_id}", response_model=ReportRead)
def get_report(report_id: str, db: Session = Depends(get_db)):
    ensure_reports_schema_columns(db)
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return _serialize_report(report)


@router.get("/{report_id}/download")
def download_report(report_id: str, db: Session = Depends(get_db)):
    ensure_reports_schema_columns(db)
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    path = _report_path(report)
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail="Report file not found")

    media_type = guess_type(path.name)[0] or "application/octet-stream"
    download_name = _safe_file_name(
        str(report.scope_payload.get("file_name") or path.name),
        fallback_stem=report.report_name,
        suffix=path.suffix.lstrip("."),
    )
    return FileResponse(path, media_type=media_type, filename=download_name)


@router.post("", response_model=ReportRead)
@router.post("/", response_model=ReportRead)
def create_report(payload: ReportCreateRequest, db: Session = Depends(get_db)):
    ensure_reports_schema_columns(db)
    total_assets = payload.total_assets if payload.total_assets is not None else len(payload.asset_ids)
    excluded_assets = payload.excluded_assets if payload.excluded_assets is not None else 0
    report = Report(
        id=str(uuid4()),
        report_name=payload.report_name,
        report_type=payload.report_formats[0] if payload.report_formats else "html",
        scope_type=payload.scope_type,
        scope_payload={
            "selection_id": payload.selection_id,
            "asset_ids": payload.asset_ids,
            "total_assets": total_assets,
            "excluded_assets": excluded_assets,
            "exclude_false_positive": payload.exclude_false_positive,
            "exclude_confirmed": payload.exclude_confirmed,
            "file_name": payload.file_name,
            "report_content": payload.report_content,
        },
        total_assets=total_assets,
        excluded_assets=excluded_assets,
        created_by=payload.created_by,
        status="running",
        object_path=None,
        file_size=None,
        finished_at=None,
        error_message=None,
    )

    db.add(report)
    db.commit()
    db.refresh(report)

    report_content = _resolve_report_content(report, payload)
    try:
        if report_content is None:
            raise ValueError("report_content is required")
        _write_report_file(report, report_content, payload.file_name)
    except Exception as exc:
        _mark_report_failed(report, str(exc), clear_file=True)
    db.commit()
    db.refresh(report)

    return _serialize_report(report)


@router.delete("/{report_id}", status_code=204)
def delete_report(report_id: str, db: Session = Depends(get_db)):
    ensure_reports_schema_columns(db)
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    path = _report_path(report)
    if path is not None and path.exists():
        path.unlink()

    db.delete(report)
    db.commit()
    return


@router.post("/{report_id}/regenerate", response_model=ReportRead)
def regenerate_report(report_id: str, db: Session = Depends(get_db)):
    ensure_reports_schema_columns(db)
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    scope_payload = getattr(report, "scope_payload", {}) or {}
    file_name = scope_payload.get("file_name")
    report_content = _resolve_report_content(report, allow_file_fallback=True)

    if report_content is None:
        path = _report_path(report)
        if path is not None and not path.exists():
            raise HTTPException(status_code=404, detail="Report file not found")
        raise HTTPException(status_code=400, detail="report_content is required for regeneration")

    report.status = "running"
    report.finished_at = None
    report.error_message = None

    try:
        _write_report_file(report, report_content, str(file_name) if file_name else None)
    except Exception as exc:
        _mark_report_failed(report, str(exc), clear_file=False)
    db.commit()
    db.refresh(report)
    return _serialize_report(report)
