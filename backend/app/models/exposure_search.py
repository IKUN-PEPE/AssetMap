from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class ExposureSearchTask(Base):
    __tablename__ = "exposure_search_tasks"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255))
    org_keywords: Mapped[list[str]] = mapped_column(JSON)
    title_keywords: Mapped[list[str]] = mapped_column(JSON)
    url_keywords: Mapped[list[str]] = mapped_column(JSON)
    file_types: Mapped[list[str]] = mapped_column(JSON)
    sources: Mapped[list[str]] = mapped_column(JSON)
    max_results: Mapped[int] = mapped_column(Integer, default=100)
    max_pages: Mapped[int] = mapped_column(Integer, default=2)
    only_documents: Mapped[bool] = mapped_column(default=False)
    only_webpages: Mapped[bool] = mapped_column(default=False)
    query_plan: Mapped[list[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    total_results: Mapped[int] = mapped_column(Integer, default=0)
    valid_count: Mapped[int] = mapped_column(Integer, default=0)
    ignored_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    results = relationship("ExposureSearchResult", back_populates="task", cascade="all, delete-orphan")


class ExposureSearchResult(Base):
    __tablename__ = "exposure_search_results"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    task_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("exposure_search_tasks.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    query: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text, index=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    risk_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    matched_keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), index=True, default="pending")  # pending / valid / ignored / imported
    imported_asset_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    task = relationship("ExposureSearchTask", back_populates="results")
