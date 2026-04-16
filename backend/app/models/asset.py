from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Host(Base):
    __tablename__ = "hosts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    ip: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    rdns: Mapped[str | None] = mapped_column(String(255), nullable=True)
    asn: Mapped[str | None] = mapped_column(String(64), nullable=True)
    isp: Mapped[str | None] = mapped_column(String(128), nullable=True)
    org_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    province: Mapped[str | None] = mapped_column(String(64), nullable=True)
    city: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    services: Mapped[list["Service"]] = relationship(back_populates="host")


class Service(Base):
    __tablename__ = "services"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    host_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("hosts.id"), index=True)
    port: Mapped[int] = mapped_column(Integer)
    protocol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    service_name: Mapped[str] = mapped_column(String(64))
    banner: Mapped[str | None] = mapped_column(Text, nullable=True)
    product: Mapped[str | None] = mapped_column(String(128), nullable=True)
    version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    host: Mapped[Host] = relationship(back_populates="services")
    web_endpoints: Mapped[list["WebEndpoint"]] = relationship(back_populates="service")


class WebEndpoint(Base):
    __tablename__ = "web_endpoints"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    host_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("hosts.id"), nullable=True)
    service_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("services.id"), nullable=True)
    normalized_url: Mapped[str] = mapped_column(Text)
    normalized_url_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    domain: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scheme: Mapped[str | None] = mapped_column(String(16), nullable=True)
    screenshot_status: Mapped[str] = mapped_column(String(32), default="none", index=True)
    label_status: Mapped[str] = mapped_column(String(32), default="none", index=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    service: Mapped[Service | None] = relationship(back_populates="web_endpoints")
    screenshots: Mapped[list["Screenshot"]] = relationship(back_populates="web_endpoint")
