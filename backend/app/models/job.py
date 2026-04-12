from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CollectJob(Base, TimestampMixin):
    __tablename__ = "collect_jobs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    job_name: Mapped[str] = mapped_column(String(128))
    sources: Mapped[dict] = mapped_column(JSONB)
    query_payload: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    created_by: Mapped[str] = mapped_column(String(64), default="system")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    observations: Mapped[list["SourceObservation"]] = relationship(back_populates="collect_job")
