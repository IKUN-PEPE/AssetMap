import logging
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models import CollectJob, Host, Service, SourceObservation, WebEndpoint
from app.services.collectors.dedup import touch_existing_web_endpoint
from app.services.normalizer.service import build_url_hash

from .collect_dedup import _find_existing_web_endpoint
from .collect_identity import (
    _build_asset_identity_key,
    _build_source_record_id,
    _build_web_source_meta,
    _ensure_saveable_identity,
    _observation_only_success_bucket,
    _safe_text,
    _serialize_observation_payload,
    _utcnow_naive,
)
from .collect_runtime import _apply_job_counters, load_job

logger = logging.getLogger(__name__)


class SaveAssetsResult:
    def __init__(self):
        self.success_count = 0
        self.duplicate_count = 0
        self.failed_count = 0
        self.observation_only_count = 0


def _upsert_source_observation(
    asset_db: Session,
    job_id: str,
    source_name: str,
    observed_at,
    source_record_id: str | None,
    raw_payload: dict[str, Any],
) -> None:
    asset_db.add(
        SourceObservation(
            collect_job_id=job_id,
            source_name=source_name,
            source_record_id=source_record_id,
            raw_payload=raw_payload,
            observed_at=observed_at,
        )
    )


def _save_asset_row_with_session(
    asset_db: Session,
    job: CollectJob,
    asset_data: Dict[str, Any],
    source_name: str,
    index: int,
    logger_ref,
) -> tuple[int, int, int, int]:
    resolved = _ensure_saveable_identity(asset_data, source_name)
    if not resolved:
        logger_ref.warning(
            "[%s] save failed row=%s reason=unresolvable-asset ip=%s host=%s domain=%s",
            source_name,
            index,
            _safe_text(asset_data.get("ip")),
            _safe_text(asset_data.get("host")),
            _safe_text(asset_data.get("domain")),
        )
        return (0, 0, 1, 0)

    observed_at = _utcnow_naive()
    normalized_url = _safe_text(resolved.get("normalized_url"))
    identity_key = _build_asset_identity_key(resolved, source_name)
    source_record_id = _build_source_record_id(source_name, resolved)
    existing_web = _find_existing_web_endpoint(asset_db, resolved)

    host_id = getattr(existing_web, "host_id", None) if existing_web else None
    service_id = getattr(existing_web, "service_id", None) if existing_web else None

    if resolved.get("ip"):
        host = asset_db.query(Host).filter(Host.ip == resolved["ip"]).first()
        if not host:
            host = Host(
                ip=resolved["ip"],
                org_name=resolved.get("company"),
                country=resolved.get("country"),
                city=resolved.get("city"),
                first_seen_at=observed_at,
                last_seen_at=observed_at,
            )
            asset_db.add(host)
            if hasattr(asset_db, "flush"):
                asset_db.flush()
        else:
            if not getattr(host, "first_seen_at", None):
                host.first_seen_at = observed_at
            host.last_seen_at = observed_at
            if not getattr(host, "org_name", None):
                host.org_name = resolved.get("company")
            if not getattr(host, "country", None):
                host.country = resolved.get("country")
            if not getattr(host, "city", None):
                host.city = resolved.get("city")
        host_id = getattr(host, "id", None)

        if host_id is not None and resolved.get("port") is not None:
            service = asset_db.query(Service).filter(Service.host_id == host_id, Service.port == resolved["port"]).first()
            if not service:
                service = Service(
                    host_id=host_id,
                    port=resolved["port"],
                    protocol=resolved.get("protocol"),
                    service_name=resolved.get("protocol") or "unknown",
                    banner=resolved.get("server"),
                    first_seen_at=observed_at,
                    last_seen_at=observed_at,
                )
                asset_db.add(service)
                if hasattr(asset_db, "flush"):
                    asset_db.flush()
            else:
                service.protocol = getattr(service, "protocol", None) or resolved.get("protocol")
                service.service_name = getattr(service, "service_name", None) or resolved.get("protocol") or "unknown"
                if not getattr(service, "banner", None):
                    service.banner = resolved.get("server")
                if not getattr(service, "first_seen_at", None):
                    service.first_seen_at = observed_at
                service.last_seen_at = observed_at
            service_id = getattr(service, "id", None)

    source_meta = _build_web_source_meta(source_name, job.id, asset_data, resolved, identity_key, source_record_id)

    if existing_web:
        try:
            touch_existing_web_endpoint(existing_web, observed_at)
        except Exception:
            pass

        if not getattr(existing_web, "domain", None):
            existing_web.domain = resolved.get("domain")
        if not getattr(existing_web, "title", None):
            existing_web.title = resolved.get("title")
        if not getattr(existing_web, "scheme", None):
            existing_web.scheme = resolved.get("protocol")
        if getattr(existing_web, "status_code", None) is None:
            existing_web.status_code = resolved.get("status_code")
        if getattr(existing_web, "host_id", None) is None and host_id is not None:
            existing_web.host_id = host_id
        if getattr(existing_web, "service_id", None) is None and service_id is not None:
            existing_web.service_id = service_id

        merged_source_meta = dict(getattr(existing_web, "source_meta", {}) or {})
        for key, value in source_meta.items():
            if key not in merged_source_meta or merged_source_meta.get(key) in (None, "", [], {}):
                merged_source_meta[key] = value
        existing_web.source_meta = merged_source_meta
        web = existing_web
        duplicate = 1
        success = 0
        observation_only = 0
        logger_ref.info(
            "[%s] save duplicate row=%s key=%s url=%s",
            source_name,
            index,
            identity_key,
            normalized_url,
        )
    elif normalized_url:
        web = WebEndpoint(
            host_id=host_id,
            service_id=service_id,
            normalized_url=normalized_url,
            normalized_url_hash=build_url_hash(normalized_url),
            domain=resolved.get("domain"),
            title=resolved.get("title"),
            status_code=resolved.get("status_code"),
            scheme=resolved.get("protocol"),
            first_seen_at=observed_at,
            last_seen_at=observed_at,
            source_meta=source_meta,
        )
        asset_db.add(web)
        if hasattr(asset_db, "flush"):
            asset_db.flush()
        duplicate = 0
        success = 1
        observation_only = 0
        logger_ref.info(
            "[%s] save success row=%s key=%s url=%s",
            source_name,
            index,
            identity_key,
            normalized_url,
        )
    elif _observation_only_success_bucket(resolved):
        web = None
        duplicate = 0
        success = 1
        observation_only = 1
        logger_ref.info(
            "[%s] save observation-only row=%s key=%s host=%s ip=%s port=%s domain=%s",
            source_name,
            index,
            identity_key,
            resolved.get("host"),
            resolved.get("ip"),
            resolved.get("port"),
            resolved.get("domain"),
        )
    else:
        logger_ref.warning(
            "[%s] save failed row=%s reason=no-saveable-identity host=%s ip=%s port=%s domain=%s",
            source_name,
            index,
            resolved.get("host"),
            resolved.get("ip"),
            resolved.get("port"),
            resolved.get("domain"),
        )
        return (0, 0, 1, 0)

    raw_payload = _serialize_observation_payload(asset_data, resolved, source_name, web)
    _upsert_source_observation(asset_db, job.id, source_name, observed_at, source_record_id, raw_payload)
    if hasattr(asset_db, "flush"):
        asset_db.flush()
    return (success, duplicate, 0, observation_only)


def _load_job_for_write(session: Session, job_id: str) -> CollectJob:
    job = load_job(session, job_id)
    if not job:
        raise ValueError(f"Job not found: {job_id}")
    return job


def _is_isolated_session_usable(db: Session) -> bool:
    return hasattr(db, "bind") and callable(getattr(db, "rollback", None))


def _rollback_session_quietly(session: Session) -> None:
    rollback = getattr(session, "rollback", None)
    if callable(rollback):
        try:
            rollback()
        except Exception:
            pass


def _sync_job_counters(target_job: CollectJob, source_job: CollectJob) -> None:
    for field in ("success_count", "duplicate_count", "failed_count", "total_count"):
        setattr(target_job, field, int(getattr(source_job, field, 0) or 0))


def _record_save_failure(
    asset_db: Session,
    job: CollectJob,
    isolated_session: Session | None,
) -> None:
    failed_job = _load_job_for_write(asset_db, job.id) if isolated_session is not None else job
    _apply_job_counters(failed_job, failed=1)
    if hasattr(asset_db, "commit"):
        asset_db.commit()
    if isolated_session is not None:
        _sync_job_counters(job, failed_job)


def _refresh_job_quietly(db: Session, job: CollectJob) -> None:
    refresh = getattr(db, "refresh", None)
    if callable(refresh):
        try:
            refresh(job)
        except Exception:
            pass


def _create_isolated_asset_session() -> Session | None:
    try:
        return SessionLocal()
    except Exception:
        return None


def save_assets(
    db: Session,
    job: CollectJob,
    assets: List[Dict[str, Any]],
    source_name: str,
    *,
    job_logger=None,
) -> SaveAssetsResult:
    result = SaveAssetsResult()
    logger_ref = job_logger or logger

    for index, asset_data in enumerate(assets, start=1):
        job_counter_snapshot = {
            field: int(getattr(job, field, 0) or 0)
            for field in ("success_count", "duplicate_count", "failed_count", "total_count")
        }
        isolated_session = _create_isolated_asset_session() if _is_isolated_session_usable(db) else None
        asset_db = isolated_session or db
        try:
            isolated_job = _load_job_for_write(asset_db, job.id) if isolated_session is not None else job
            success, duplicate, failed, observation_only = _save_asset_row_with_session(
                asset_db,
                isolated_job,
                asset_data,
                source_name,
                index,
                logger_ref,
            )
            result.success_count += success
            result.duplicate_count += duplicate
            result.failed_count += failed
            result.observation_only_count += observation_only

            _apply_job_counters(isolated_job, success=success, duplicate=duplicate, failed=failed)
            if hasattr(asset_db, "commit"):
                asset_db.commit()
            if isolated_session is not None:
                _sync_job_counters(job, isolated_job)
        except Exception as exc:
            _rollback_session_quietly(asset_db)
            failure_counted = False
            try:
                _record_save_failure(asset_db, job, isolated_session)
                failure_counted = True
            except Exception:
                _rollback_session_quietly(asset_db)
                try:
                    _rollback_session_quietly(db)
                    for field, value in job_counter_snapshot.items():
                        setattr(job, field, value)
                    _apply_job_counters(job, failed=1)
                    if callable(getattr(db, "commit", None)):
                        db.commit()
                    failure_counted = True
                except Exception:
                    _rollback_session_quietly(db)
                    for field, value in job_counter_snapshot.items():
                        setattr(job, field, value)
                    _apply_job_counters(job, failed=1)
                    failure_counted = True
            if failure_counted:
                result.failed_count += 1
            logger_ref.exception("[%s] save failed row=%s reason=%s", source_name, index, exc)
        finally:
            if isolated_session is not None:
                isolated_session.close()

    _refresh_job_quietly(db, job)

    logger_ref.info(
        "[%s] save summary success=%s duplicate=%s failed=%s observation_only=%s total=%s",
        source_name,
        result.success_count,
        result.duplicate_count,
        result.failed_count,
        result.observation_only_count,
        int(getattr(job, "total_count", 0) or 0),
    )
    return result
