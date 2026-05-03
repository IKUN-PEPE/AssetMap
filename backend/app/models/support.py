from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class SystemConfig(Base):
    __tablename__ = "system_configs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    config_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    config_value: Mapped[str] = mapped_column(Text, default="")
    config_group: Mapped[str] = mapped_column(String(64), index=True, default="system")
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SourceObservation(Base):
    __tablename__ = "source_observations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    collect_job_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("collect_jobs.id"), index=True)
    source_name: Mapped[str] = mapped_column(String(32), index=True)
    source_record_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSONB)
    quota_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    collect_job = relationship("CollectJob", back_populates="observations")


class JobPendingAsset(Base):
    __tablename__ = "job_pending_assets"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    job_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("collect_jobs.id"), index=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    raw_data: Mapped[dict] = mapped_column(JSONB)
    mapped_data: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(32), index=True, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Screenshot(Base):
    __tablename__ = "screenshots"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    web_endpoint_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("web_endpoints.id"), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    object_path: Mapped[str] = mapped_column(Text)
    file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    web_endpoint = relationship("WebEndpoint", back_populates="screenshots")


class Label(Base):
    __tablename__ = "labels"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    asset_type: Mapped[str] = mapped_column(String(32), default="web_endpoint")
    asset_id: Mapped[str] = mapped_column(UUID(as_uuid=False), index=True)
    label_type: Mapped[str] = mapped_column(String(32), index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(64), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LabelAuditLog(Base):
    __tablename__ = "label_audit_logs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    batch_id: Mapped[str] = mapped_column(String(64), index=True)
    asset_type: Mapped[str] = mapped_column(String(32))
    asset_id: Mapped[str] = mapped_column(UUID(as_uuid=False), index=True)
    before_label: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_label: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    action_type: Mapped[str] = mapped_column(String(32))
    operator: Mapped[str] = mapped_column(String(64), default="system")
    operated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SavedSelection(Base):
    __tablename__ = "saved_selections"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    selection_name: Mapped[str] = mapped_column(String(128))
    selection_type: Mapped[str] = mapped_column(String(32))
    filter_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SelectionItem(Base):
    __tablename__ = "selection_items"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    selection_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("saved_selections.id"), index=True)
    asset_type: Mapped[str] = mapped_column(String(32), default="web_endpoint")
    asset_id: Mapped[str] = mapped_column(UUID(as_uuid=False), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    report_name: Mapped[str] = mapped_column(String(255))
    report_type: Mapped[str] = mapped_column(String(32), default="html")
    scope_type: Mapped[str] = mapped_column(String(32))
    scope_payload: Mapped[dict] = mapped_column(JSONB)
    object_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_assets: Mapped[int] = mapped_column(Integer, default=0)
    excluded_assets: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(64), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
