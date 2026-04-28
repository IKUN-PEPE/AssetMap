import logging
from datetime import datetime
from pathlib import Path
from typing import Any, List

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import desc, inspect, or_
from sqlalchemy.orm import Session

from app.api.assets import serialize_asset
from app.core.config import BASE_DIR
from app.core.db import get_db
from app.core.huey import run_in_process
from app.models import CollectJob, Host, JobPendingAsset, Service, SourceObservation, WebEndpoint
from app.schemas.job import (
    JobBatchIdsRequest,
    JobBatchOperationResponse,
    CollectJobCreate,
    CollectJobDetail,
    CollectJobRead,
    JobConfirmImportRequest,
    JobConfirmImportResponse,
    JobDiscardImportResponse,
    JobLogResponse,
    JobPendingAssetListResponse,
    JobPendingAssetRead,
    JobResultPreviewResponse,
    JobTaskDetails,
)
from app.services.collectors.preview import get_csv_preview
from app.services.normalizer.service import normalize_url
from app.tasks.collect_persistence import save_assets
from app.tasks.sample_import import import_sample_assets

router = APIRouter()
logger = logging.getLogger(__name__)

UPLOAD_DIR = BASE_DIR / "tmp_uploads"
LOGS_DIR = BASE_DIR / "logs"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)


def ensure_job_pending_assets_schema(db: Session) -> None:
    bind = getattr(db, "bind", None)
    if bind is None:
        return
    inspector = inspect(bind)
    try:
        tables = set(inspector.get_table_names())
    except Exception:
        return
    if "job_pending_assets" in tables:
        return
    JobPendingAsset.__table__.create(bind=bind, checkfirst=True)


def construct_command_line(job: CollectJob) -> str:
    if "csv_import" in job.sources:
        source_type = (job.query_payload or {}).get("source_type") or "mapped"
        return f"import --source {source_type} --file {(job.query_payload or {}).get('file_path', '')}"

    commands = []
    queries = (job.query_payload or {}).get("queries", [])
    for q_item in queries:
        source = q_item.get("source")
        query = q_item.get("query")
        if source and query:
            commands.append(f'{source} --query "{query}"')
    return " | ".join(commands)


def _get_job_or_404(db: Session, job_id: str) -> CollectJob:
    job = db.get(CollectJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _get_log_content(job_id: str) -> tuple[str, bool]:
    log_file = LOGS_DIR / f"{job_id}.log"
    if not log_file.exists():
        return "", False
    return log_file.read_text(encoding="utf-8", errors="replace"), True


def _serialize_pending_asset(item: JobPendingAsset) -> dict[str, Any]:
    mapped = dict(getattr(item, "mapped_data", {}) or {})
    return {
        "id": item.id,
        "source": item.source,
        "normalized_url": mapped.get("url") or mapped.get("normalized_url"),
        "url": mapped.get("url"),
        "domain": mapped.get("domain"),
        "ip": mapped.get("ip"),
        "port": mapped.get("port"),
        "title": mapped.get("title"),
        "status_code": mapped.get("status_code"),
        "protocol": mapped.get("protocol"),
        "country": mapped.get("country"),
        "city": mapped.get("city"),
        "org": mapped.get("org"),
        "status": item.status,
        "created_at": item.created_at,
    }


def _pending_assets_query(db: Session, job_id: str):
    ensure_job_pending_assets_schema(db)
    return db.query(JobPendingAsset).filter(JobPendingAsset.job_id == job_id)


def _job_can_delete(job: CollectJob) -> bool:
    return job.status in {"success", "failed", "cancelled", "partial_success", "pending_import", "imported", "discarded"}


def _job_can_rerun(job: CollectJob) -> bool:
    return job.status in {"success", "failed", "cancelled", "partial_success", "imported", "discarded"}


def _job_can_start(job: CollectJob) -> bool:
    return job.status in {"pending"}


def _stage_state(*, enabled: bool, started: bool, finished: bool, success_count: int, failed_count: int) -> str:
    if not enabled:
        return "disabled"
    if not started:
        return "pending"
    if started and not finished:
        return "running"
    if success_count > 0 and failed_count > 0:
        return "partial_failed"
    if success_count > 0:
        return "success"
    if failed_count > 0:
        return "failed"
    return "failed"


def _extract_last_stage_error(log_content: str, marker: str) -> str | None:
    last_error = None
    for line in log_content.splitlines():
        if marker not in line:
            continue
        if " reason=" in line:
            last_error = line.split(" reason=", 1)[1].strip() or None
    return last_error


def _prefer_db_stat(db_value: int | None, log_value: int) -> int:
    return db_value if db_value is not None else log_value


def _prefer_db_stage_started(started_count: int | None, log_started: bool) -> bool:
    if started_count is not None:
        if started_count > 0:
            return True
        return log_started
    return log_started


def _prefer_db_stage_finished(
    *,
    started_count: int | None,
    success_count: int | None,
    failed_count: int | None,
    log_finished: bool,
) -> bool:
    if started_count is not None or success_count is not None or failed_count is not None:
        total_started = int(started_count or 0)
        total_processed = int(success_count or 0) + int(failed_count or 0)
        if total_started <= 0:
            return log_finished
        return total_processed >= total_started
    return log_finished


def _prefer_db_stage_error(
    *,
    started_count: int | None,
    failed_count: int | None,
    db_error: str | None,
    log_content: str,
    marker: str,
) -> str | None:
    if failed_count is None:
        return db_error or _extract_last_stage_error(log_content, marker)
    if failed_count > 0:
        return db_error or _extract_last_stage_error(log_content, marker)
    if started_count is not None and started_count <= 0:
        return _extract_last_stage_error(log_content, marker)
    return None


def _safe_port(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _normalize_candidate_url(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return normalize_url(raw)
    except Exception:
        return raw


def _observation_candidate_keys(obs: SourceObservation) -> dict[str, Any]:
    raw_payload = obs.raw_payload or {}
    return {
        "web_endpoint_id": raw_payload.get("web_endpoint_id") or raw_payload.get("id"),
        "source_record_id": getattr(obs, "source_record_id", None) or raw_payload.get("source_record_id"),
        "normalized_url": _normalize_candidate_url(
            raw_payload.get("normalized_url")
            or raw_payload.get("entry_url")
            or raw_payload.get("fallback_url")
            or raw_payload.get("url")
        ),
        "asset_identity_key": raw_payload.get("asset_identity_key"),
        "domain": raw_payload.get("resolved_domain") or raw_payload.get("domain"),
        "host": raw_payload.get("resolved_host") or raw_payload.get("host"),
        "ip": raw_payload.get("resolved_ip") or raw_payload.get("ip"),
        "port": _safe_port(raw_payload.get("resolved_port") or raw_payload.get("port")),
    }


def _build_result_lookup_indexes(assets: list[WebEndpoint]) -> dict[str, dict[Any, WebEndpoint]]:
    by_id: dict[Any, WebEndpoint] = {}
    by_url: dict[Any, WebEndpoint] = {}
    by_identity: dict[Any, WebEndpoint] = {}
    by_source_record: dict[Any, WebEndpoint] = {}
    by_domain_port: dict[Any, WebEndpoint] = {}
    by_ip_port: dict[Any, WebEndpoint] = {}
    by_host_port: dict[Any, WebEndpoint] = {}
    by_domain: dict[Any, WebEndpoint] = {}
    by_ip: dict[Any, WebEndpoint] = {}
    by_host: dict[Any, WebEndpoint] = {}

    for asset in assets:
        asset_id = getattr(asset, "id", None)
        if asset_id is not None:
            by_id[asset_id] = asset

        raw_url = getattr(asset, "normalized_url", None)
        if raw_url:
            by_url[raw_url] = asset
            normalized_lookup_url = _normalize_candidate_url(raw_url)
            if normalized_lookup_url:
                by_url[normalized_lookup_url] = asset

        source_meta = getattr(asset, "source_meta", {}) or {}
        service = getattr(asset, "service", None)
        host_obj = getattr(service, "host", None) if service else getattr(asset, "host", None)
        domain = getattr(asset, "domain", None) or source_meta.get("domain")
        ip = (getattr(host_obj, "ip", None) if host_obj else None) or source_meta.get("ip")
        port = _safe_port((getattr(service, "port", None) if service else None) or source_meta.get("port"))
        identity_key = source_meta.get("asset_identity_key")
        if identity_key:
            by_identity[identity_key] = asset
        source_record_id = source_meta.get("source_record_id")
        if source_record_id:
            by_source_record[source_record_id] = asset
        host = source_meta.get("host") or source_meta.get("subdomain") or domain or ip

        if domain:
            by_domain[domain] = asset
        if ip:
            by_ip[ip] = asset
        if host:
            by_host[host] = asset
        if domain and port is not None:
            by_domain_port[(domain, port)] = asset
        if ip and port is not None:
            by_ip_port[(ip, port)] = asset
        if host and port is not None:
            by_host_port[(host, port)] = asset

    return {
        "by_id": by_id,
        "by_url": by_url,
        "by_identity": by_identity,
        "by_source_record": by_source_record,
        "by_domain_port": by_domain_port,
        "by_ip_port": by_ip_port,
        "by_host_port": by_host_port,
        "by_domain": by_domain,
        "by_ip": by_ip,
        "by_host": by_host,
    }


def _resolve_asset_from_observation(obs: SourceObservation, indexes: dict[str, dict[Any, WebEndpoint]]) -> WebEndpoint | None:
    keys = _observation_candidate_keys(obs)
    candidate = None
    if keys["web_endpoint_id"]:
        candidate = indexes["by_id"].get(keys["web_endpoint_id"])
    if candidate is None and keys["source_record_id"]:
        candidate = indexes["by_source_record"].get(keys["source_record_id"])
    if candidate is None and keys["normalized_url"]:
        candidate = indexes["by_url"].get(keys["normalized_url"])
    if candidate is None and keys["asset_identity_key"]:
        candidate = indexes["by_identity"].get(keys["asset_identity_key"])
    if candidate is None and keys["domain"] and keys["port"] is not None:
        candidate = indexes["by_domain_port"].get((keys["domain"], keys["port"]))
    if candidate is None and keys["host"] and keys["port"] is not None:
        candidate = indexes["by_host_port"].get((keys["host"], keys["port"]))
    if candidate is None and keys["ip"] and keys["port"] is not None:
        candidate = indexes["by_ip_port"].get((keys["ip"], keys["port"]))
    if candidate is None and keys["domain"]:
        candidate = indexes["by_domain"].get(keys["domain"])
    if candidate is None and keys["host"]:
        candidate = indexes["by_host"].get(keys["host"])
    if candidate is None and keys["ip"]:
        candidate = indexes["by_ip"].get(keys["ip"])
    return candidate


def _build_observation_asset_query(db: Session, observations: list[SourceObservation]):
    query = db.query(WebEndpoint)
    joins_available = callable(getattr(query, "outerjoin", None))
    if joins_available:
        query = query.outerjoin(Service, WebEndpoint.service_id == Service.id).outerjoin(Host, WebEndpoint.host_id == Host.id)

    def _port_match(port: int):
        clauses = [WebEndpoint.source_meta["port"].astext == str(port)]
        if joins_available:
            clauses.append(Service.port == port)
        return or_(*clauses)

    def _ip_match(ip: str):
        clauses = [WebEndpoint.source_meta["ip"].astext == ip]
        if joins_available:
            clauses.append(Host.ip == ip)
        return or_(*clauses)

    def _domain_match(domain: str):
        clauses = [WebEndpoint.domain == domain, WebEndpoint.source_meta["domain"].astext == domain]
        return or_(*clauses)

    ids: set[str] = set()
    source_record_ids: set[str] = set()
    urls: set[str] = set()
    identity_keys: set[str] = set()
    domains: set[str] = set()
    hosts: set[str] = set()
    ips: set[str] = set()
    domain_port_pairs: set[tuple[str, int]] = set()
    host_port_pairs: set[tuple[str, int]] = set()
    ip_port_pairs: set[tuple[str, int]] = set()
    for obs in observations:
        keys = _observation_candidate_keys(obs)
        if keys["web_endpoint_id"]:
            ids.add(str(keys["web_endpoint_id"]))
        if keys["source_record_id"]:
            source_record_ids.add(str(keys["source_record_id"]))
        if keys["normalized_url"]:
            urls.add(str(keys["normalized_url"]))
        if keys["asset_identity_key"]:
            identity_keys.add(str(keys["asset_identity_key"]))
        if keys["domain"]:
            domains.add(str(keys["domain"]))
            if keys["port"] is not None:
                domain_port_pairs.add((str(keys["domain"]), int(keys["port"])))
        if keys["host"]:
            hosts.add(str(keys["host"]))
            if keys["port"] is not None:
                host_port_pairs.add((str(keys["host"]), int(keys["port"])))
        if keys["ip"]:
            ips.add(str(keys["ip"]))
            if keys["port"] is not None:
                ip_port_pairs.add((str(keys["ip"]), int(keys["port"])))
    filters = []
    if ids:
        filters.append(WebEndpoint.id.in_(sorted(ids)))
    if urls:
        filters.append(WebEndpoint.normalized_url.in_(sorted(urls)))
    if domain_port_pairs:
        filters.append(
            or_(
                *[
                    (
                        _domain_match(domain)
                        & _port_match(port)
                    )
                    for domain, port in sorted(domain_port_pairs)
                ]
            )
        )
    if host_port_pairs:
        filters.append(
            or_(
                *[
                    (
                        (
                            (WebEndpoint.source_meta["host"].astext == host)
                            | (WebEndpoint.source_meta["subdomain"].astext == host)
                            | (WebEndpoint.domain == host)
                            | (WebEndpoint.source_meta["domain"].astext == host)
                        )
                        & _port_match(port)
                    )
                    for host, port in sorted(host_port_pairs)
                ]
            )
        )
    if ip_port_pairs:
        filters.append(
            or_(
                *[
                    (
                        _ip_match(ip)
                        & _port_match(port)
                    )
                    for ip, port in sorted(ip_port_pairs)
                ]
            )
        )
    if domains:
        filters.append(or_(WebEndpoint.domain.in_(sorted(domains)), WebEndpoint.source_meta["domain"].astext.in_(sorted(domains))))
    if source_record_ids:
        filters.append(WebEndpoint.source_meta["source_record_id"].astext.in_(sorted(source_record_ids)))
    if identity_keys:
        filters.append(WebEndpoint.source_meta["asset_identity_key"].astext.in_(sorted(identity_keys)))
    if hosts:
        filters.append(
            or_(
                WebEndpoint.source_meta["host"].astext.in_(sorted(hosts)),
                WebEndpoint.source_meta["subdomain"].astext.in_(sorted(hosts)),
                WebEndpoint.domain.in_(sorted(hosts)),
                WebEndpoint.source_meta["domain"].astext.in_(sorted(hosts)),
            )
        )
    if ips:
        ip_filters = [WebEndpoint.source_meta["ip"].astext.in_(sorted(ips))]
        if joins_available:
            ip_filters.append(Host.ip.in_(sorted(ips)))
        filters.append(or_(*ip_filters))

    if filters:
        return query.filter(or_(*filters))
    return query.filter(WebEndpoint.id.in_([]))


def _build_job_scoped_asset_query(db: Session, job_id: str):
    return db.query(WebEndpoint).filter(
        or_(
            WebEndpoint.source_meta["import_job_id"].astext == str(job_id),
            WebEndpoint.source_meta["post_process_job_id"].astext == str(job_id),
            WebEndpoint.source_meta["post_process_job_ids"].contains([str(job_id)]),
        )
    )


def _collect_candidate_assets(job_id: str, db: Session, observations: list[SourceObservation]) -> list[WebEndpoint]:
    assets_by_id: dict[str, WebEndpoint] = {}

    for asset in _build_job_scoped_asset_query(db, job_id).all():
        assets_by_id[asset.id] = asset

    for asset in _build_observation_asset_query(db, observations).all():
        assets_by_id[asset.id] = asset

    return list(assets_by_id.values())


def _collect_result_assets(job_id: str, db: Session) -> list[WebEndpoint]:
    observations = (
        db.query(SourceObservation)
        .filter(SourceObservation.collect_job_id == job_id)
        .order_by(desc(SourceObservation.created_at))
        .all()
    )
    if not observations:
        return []

    assets = _collect_candidate_assets(job_id, db, observations)
    indexes = _build_result_lookup_indexes(assets)
    ordered_assets: list[WebEndpoint] = []
    seen: set[str] = set()

    for obs in observations:
        asset = _resolve_asset_from_observation(obs, indexes)
        if asset is None or asset.id in seen:
            continue
        seen.add(asset.id)
        ordered_assets.append(asset)

    return ordered_assets


def _collect_post_process_asset_stats(job_id: str, db: Session) -> dict[str, Any]:
    assets = _build_job_scoped_asset_query(db, job_id).all()

    verify_success = 0
    verify_failed = 0
    screenshot_success = 0
    screenshot_failed = 0
    verify_last_error = None
    screenshot_last_error = None
    verify_started_count = 0
    screenshot_started_count = 0

    for asset in assets:
        source_meta = dict(getattr(asset, "source_meta", {}) or {})
        verify_error = source_meta.get("verify_error")
        screenshot_error = source_meta.get("screenshot_error")
        screenshot_status = getattr(asset, "screenshot_status", None)
        linked_job_ids = [str(item) for item in (source_meta.get("post_process_job_ids") or []) if item not in (None, "")]
        verify_job_ids = [str(item) for item in (source_meta.get("verify_job_ids") or []) if item not in (None, "")]
        screenshot_job_ids = [str(item) for item in (source_meta.get("screenshot_job_ids") or []) if item not in (None, "")]
        current_job_linked = source_meta.get("post_process_job_id") == job_id or job_id in linked_job_ids
        legacy_current_job_linked = source_meta.get("post_process_job_id") == job_id
        verify_linked = job_id in verify_job_ids
        screenshot_linked = job_id in screenshot_job_ids

        if not verify_linked and legacy_current_job_linked and (verify_error is not None or getattr(asset, "verified", False)):
            verify_linked = True
        if not screenshot_linked and legacy_current_job_linked and (
            screenshot_status == "success" or screenshot_status == "failed" or screenshot_error
        ):
            screenshot_linked = True

        if verify_linked:
            verify_started_count += 1
        if screenshot_linked:
            screenshot_started_count += 1

        if verify_linked and getattr(asset, "verified", False):
            verify_success += 1
        elif verify_linked and verify_error:
            verify_failed += 1
            verify_last_error = str(verify_error)

        if screenshot_linked and screenshot_status == "success":
            screenshot_success += 1
        elif screenshot_linked and (screenshot_status == "failed" or screenshot_error):
            screenshot_failed += 1
            screenshot_last_error = str(screenshot_error or "截图失败")

    return {
        "asset_count": len(assets),
        "verify_started_count": verify_started_count,
        "screenshot_started_count": screenshot_started_count,
        "verify_success": verify_success,
        "verify_failed": verify_failed,
        "screenshot_success": screenshot_success,
        "screenshot_failed": screenshot_failed,
        "verify_last_error": verify_last_error,
        "screenshot_last_error": screenshot_last_error,
    }


def _summarize_task_details(
    job: CollectJob,
    log_content: str,
    db: Session,
    *,
    result_asset_count: int | None = None,
) -> JobTaskDetails:
    observations_count = (
        db.query(SourceObservation)
        .filter(SourceObservation.collect_job_id == job.id)
        .count()
    )
    if result_asset_count is None:
        result_asset_count = len(_collect_result_assets(job.id, db))

    post_stats = _collect_post_process_asset_stats(job.id, db) if job.auto_verify else {
        "asset_count": 0,
        "verify_success": 0,
        "verify_failed": 0,
        "screenshot_success": 0,
        "screenshot_failed": 0,
        "verify_last_error": None,
        "screenshot_last_error": None,
    }

    log_verify_success = log_content.count("Verify success")
    log_verify_failed = log_content.count("Verify failed")
    log_screenshot_success = log_content.count("Screenshot success")
    log_screenshot_failed = log_content.count("Screenshot failed")

    verify_success = _prefer_db_stat(post_stats["verify_success"], log_verify_success)
    verify_failed = _prefer_db_stat(post_stats["verify_failed"], log_verify_failed)
    screenshot_success = _prefer_db_stat(post_stats["screenshot_success"], log_screenshot_success)
    screenshot_failed = _prefer_db_stat(post_stats["screenshot_failed"], log_screenshot_failed)
    verify_started_count = post_stats.get("verify_started_count")
    screenshot_started_count = post_stats.get("screenshot_started_count")
    verify_use_log_counts = bool(
        verify_started_count is not None
        and verify_started_count <= 0
        and int(post_stats.get("verify_success") or 0) == 0
        and int(post_stats.get("verify_failed") or 0) == 0
        and ("Auto verify start" in log_content or "Verify post-process finished" in log_content or "Auto verify finished" in log_content)
    )
    screenshot_use_log_counts = bool(
        screenshot_started_count is not None
        and screenshot_started_count <= 0
        and int(post_stats.get("screenshot_success") or 0) == 0
        and int(post_stats.get("screenshot_failed") or 0) == 0
        and (
            "Screenshot post-process start" in log_content
            or "Screenshot post-process finished" in log_content
            or "Auto verify finished" in log_content
        )
    )
    verify_state_success = log_verify_success if verify_use_log_counts else verify_success
    verify_state_failed = log_verify_failed if verify_use_log_counts else verify_failed
    screenshot_state_success = log_screenshot_success if screenshot_use_log_counts else screenshot_success
    screenshot_state_failed = log_screenshot_failed if screenshot_use_log_counts else screenshot_failed

    verify_started = bool(
        job.auto_verify
        and _prefer_db_stage_started(
            verify_started_count,
            "Auto verify start" in log_content,
        )
    )
    verify_finished = bool(
        job.auto_verify
        and _prefer_db_stage_finished(
            started_count=verify_started_count,
            success_count=post_stats.get("verify_success"),
            failed_count=post_stats.get("verify_failed"),
            log_finished=("Verify post-process finished" in log_content or "Auto verify finished" in log_content),
        )
    )
    screenshot_started = bool(
        job.auto_verify
        and _prefer_db_stage_started(
            screenshot_started_count,
            "Screenshot post-process start" in log_content,
        )
    )
    screenshot_finished = bool(
        job.auto_verify
        and _prefer_db_stage_finished(
            started_count=screenshot_started_count,
            success_count=post_stats.get("screenshot_success"),
            failed_count=post_stats.get("screenshot_failed"),
            log_finished=("Screenshot post-process finished" in log_content or "Auto verify finished" in log_content),
        )
    )
    overall_finished = bool(
        job.auto_verify
        and (
            (verify_finished and (not screenshot_started or screenshot_finished))
            or (
                post_stats.get("verify_success") is None
                and post_stats.get("verify_failed") is None
                and post_stats.get("screenshot_success") is None
                and post_stats.get("screenshot_failed") is None
                and "Auto verify finished" in log_content
            )
        )
    )

    verify_state = _stage_state(
        enabled=bool(job.auto_verify),
        started=verify_started,
        finished=verify_finished,
        success_count=verify_state_success,
        failed_count=verify_state_failed,
    )
    screenshot_state = _stage_state(
        enabled=bool(job.auto_verify),
        started=screenshot_started,
        finished=screenshot_finished,
        success_count=screenshot_state_success,
        failed_count=screenshot_state_failed,
    )
    post_process_state = _stage_state(
        enabled=bool(job.auto_verify),
        started=verify_started or screenshot_started,
        finished=overall_finished,
        success_count=verify_state_success + screenshot_state_success,
        failed_count=verify_state_failed + screenshot_state_failed,
    )

    return JobTaskDetails.model_validate(
        {
            "collection": {
                "status": job.status,
                "progress": job.progress,
                "observation_count": observations_count,
                "result_asset_count": result_asset_count,
            },
            "post_process": {
                "enabled": bool(job.auto_verify),
                "state": post_process_state,
                "verify": {
                    "state": verify_state,
                    "started": verify_started,
                    "finished": verify_finished,
                    "success": verify_success,
                    "failed": verify_failed,
                    "last_error": _prefer_db_stage_error(
                        started_count=verify_started_count,
                        failed_count=post_stats.get("verify_failed"),
                        db_error=post_stats.get("verify_last_error"),
                        log_content=log_content,
                        marker="Verify failed",
                    ),
                },
                "screenshot": {
                    "state": screenshot_state,
                    "started": screenshot_started,
                    "finished": screenshot_finished,
                    "success": screenshot_success,
                    "failed": screenshot_failed,
                    "last_error": _prefer_db_stage_error(
                        started_count=screenshot_started_count,
                        failed_count=post_stats.get("screenshot_failed"),
                        db_error=post_stats.get("screenshot_last_error"),
                        log_content=log_content,
                        marker="Screenshot failed",
                    ),
                },
            },
        }
    )


def _has_valid_queries(queries: list[dict] | None) -> bool:
    if not isinstance(queries, list):
        return False
    return any(
        str((item or {}).get("source") or "").strip() and str((item or {}).get("query") or "").strip()
        for item in queries
    )


def _compute_log_state(job: CollectJob, content: str, exists: bool) -> str:
    if job.started_at is None:
        return "not_started"
    if not exists:
        if job.status == "running":
            return "running"
        return "log_not_found"
    if not content.strip():
        if job.status == "running":
            return "running"
        return "log_empty"
    if job.status == "running":
        return "running"
    return "finished" if job.finished_at else "log_ready"


def _build_job_result_preview_item(asset: WebEndpoint) -> dict:
    base = serialize_asset(asset)
    source_meta = getattr(asset, "source_meta", {}) or {}
    service = getattr(asset, "service", None)
    host_obj = getattr(service, "host", None) if service else getattr(asset, "host", None)
    return {
        "id": base["id"],
        "source": base.get("source") or source_meta.get("source"),
        "normalized_url": base["normalized_url"],
        "url": base["normalized_url"],
        "domain": getattr(asset, "domain", None) or source_meta.get("domain") or source_meta.get("host"),
        "ip": (getattr(host_obj, "ip", None) if host_obj else None) or source_meta.get("ip"),
        "port": _safe_port((getattr(service, "port", None) if service else None) or source_meta.get("port")),
        "title": getattr(asset, "title", None),
        "status_code": getattr(asset, "status_code", None),
        "verified": base.get("verified"),
        "screenshot_status": base.get("screenshot_status"),
        "verify_error": base.get("verify_error"),
        "screenshot_error": base.get("screenshot_error"),
    }


def _build_job_result_preview_item_from_observation(obs: SourceObservation) -> dict:
    raw_payload = obs.raw_payload or {}
    normalized_url = (
        raw_payload.get("normalized_url")
        or raw_payload.get("fallback_url")
        or raw_payload.get("url")
        or raw_payload.get("resolved_domain")
        or raw_payload.get("resolved_host")
        or raw_payload.get("resolved_ip")
        or "unknown"
    )
    return {
        "id": getattr(obs, "id", None) or getattr(obs, "source_record_id", None) or raw_payload.get("source_record_id") or raw_payload.get("asset_identity_key") or normalized_url,
        "source": raw_payload.get("source") or getattr(obs, "source_name", None),
        "normalized_url": normalized_url,
        "url": raw_payload.get("url") or normalized_url,
        "domain": raw_payload.get("resolved_domain") or raw_payload.get("domain"),
        "ip": raw_payload.get("resolved_ip") or raw_payload.get("ip"),
        "port": _safe_port(raw_payload.get("resolved_port") or raw_payload.get("port")),
        "title": raw_payload.get("title"),
        "status_code": raw_payload.get("status_code"),
        "verified": None,
        "screenshot_status": None,
        "verify_error": raw_payload.get("verify_error"),
        "screenshot_error": raw_payload.get("screenshot_error"),
    }


def _collect_result_preview_items(job_id: str, db: Session) -> list[dict]:
    observations = (
        db.query(SourceObservation)
        .filter(SourceObservation.collect_job_id == job_id)
        .order_by(desc(SourceObservation.created_at))
        .all()
    )
    if not observations:
        return []

    assets = _collect_candidate_assets(job_id, db, observations)
    indexes = _build_result_lookup_indexes(assets)
    items: list[dict] = []
    seen_keys: set[str] = set()

    for obs in observations:
        asset = _resolve_asset_from_observation(obs, indexes)
        if asset is not None:
            dedup_key = f"asset:{asset.id}"
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            items.append(_build_job_result_preview_item(asset))
            continue

        fallback_item = _build_job_result_preview_item_from_observation(obs)
        dedup_key = (
            f"obs:{fallback_item['id']}:{fallback_item['normalized_url']}:"
            f"{fallback_item.get('domain')}:{fallback_item.get('ip')}:{fallback_item.get('port')}"
        )
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)
        items.append(fallback_item)

    return items


@router.get("/", response_model=List[CollectJobRead])
async def list_jobs(db: Session = Depends(get_db)):
    return db.query(CollectJob).order_by(desc(CollectJob.created_at)).all()


@router.get("/{job_id}", response_model=CollectJobDetail)
def get_collect_job(job_id: str, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    log_content, _exists = _get_log_content(job_id)

    detail = CollectJobDetail.model_validate(job)
    if job.started_at and job.finished_at:
        detail.duration = (job.finished_at - job.started_at).total_seconds()
    detail.command_line = construct_command_line(job)
    detail.task_details = _summarize_task_details(job, log_content, db)
    return detail


@router.get("/{job_id}/logs", response_model=JobLogResponse)
def get_job_logs(job_id: str, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    log_content, exists = _get_log_content(job_id)
    task_details = _summarize_task_details(job, log_content, db)
    return {
        "job_id": job_id,
        "log_state": _compute_log_state(job, log_content, exists),
        "content": log_content,
        "exists": exists,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "task_details": task_details,
    }


@router.get("/{job_id}/results", response_model=JobResultPreviewResponse)
def get_job_results(
    job_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    job = _get_job_or_404(db, job_id)
    log_content, _exists = _get_log_content(job_id)
    preview_items = _collect_result_preview_items(job_id, db)
    total = len(preview_items)
    task_details = _summarize_task_details(job, log_content, db, result_asset_count=total)
    items = preview_items[skip : skip + limit]
    return {
        "job_id": job_id,
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit,
        "task_details": task_details,
    }


@router.get("/{job_id}/pending-assets", response_model=JobPendingAssetListResponse)
def get_job_pending_assets(
    job_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    _get_job_or_404(db, job_id)
    query = _pending_assets_query(db, job_id).order_by(desc(JobPendingAsset.created_at))
    items = query.offset(skip).limit(limit).all()
    total = query.count()
    return {
        "job_id": job_id,
        "items": [_serialize_pending_asset(item) for item in items],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.post("/{job_id}/confirm-import", response_model=JobConfirmImportResponse)
def confirm_job_import(job_id: str, payload: JobConfirmImportRequest, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    ensure_job_pending_assets_schema(db)
    if job.status != "pending_import":
        raise HTTPException(status_code=400, detail="Job is not waiting for import confirmation")

    query = _pending_assets_query(db, job_id).filter(JobPendingAsset.status == "pending")
    pending_items = query.all()
    if not pending_items:
        raise HTTPException(status_code=400, detail="No pending assets to import")

    if payload.import_all:
        target_items = pending_items
    else:
        if not payload.ids:
            raise HTTPException(status_code=400, detail="ids is required when import_all is false")
        target_ids = set(payload.ids)
        target_items = [item for item in pending_items if item.id in target_ids]
        if not target_items:
            raise HTTPException(status_code=400, detail="No matching pending assets to import")

    job.success_count = 0
    job.duplicate_count = 0
    job.failed_count = 0
    job.total_count = 0

    grouped_records: dict[str, list[dict[str, Any]]] = {}
    for item in target_items:
        mapped = dict(item.mapped_data or {})
        if "raw_data" not in mapped or mapped.get("raw_data") is None:
            mapped["raw_data"] = dict(item.raw_data or {})
        grouped_records.setdefault(item.source, []).append(mapped)

    for source_name, records in grouped_records.items():
        save_assets(db, job, records, source_name)

    for item in target_items:
        item.status = "imported"
        item.imported_at = datetime.utcnow()

    remaining_pending = _pending_assets_query(db, job_id).filter(JobPendingAsset.status == "pending").count()
    job.status = "imported" if remaining_pending == 0 else "pending_import"
    db.commit()

    if bool(getattr(job, "auto_verify", False)) and job.status == "imported":
        from app.tasks.collect import run_auto_post_process
        run_in_process(run_auto_post_process, job.id, delay=2)

    return {
        "job_id": job_id,
        "total": len(target_items),
        "success": int(job.success_count or 0),
        "duplicate": int(job.duplicate_count or 0),
        "failed": int(job.failed_count or 0),
        "status": job.status,
    }


@router.post("/{job_id}/discard-import", response_model=JobDiscardImportResponse)
def discard_job_import(job_id: str, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    ensure_job_pending_assets_schema(db)
    if job.status != "pending_import":
        raise HTTPException(status_code=400, detail="Job is not waiting for import confirmation")

    pending_items = _pending_assets_query(db, job_id).filter(JobPendingAsset.status == "pending").all()
    discarded = 0
    for item in pending_items:
        item.status = "discarded"
        discarded += 1
    job.status = "discarded"
    db.commit()
    return {"job_id": job_id, "discarded": discarded, "status": job.status}


@router.post("/preview")
async def preview_csv(file: UploadFile = File(...)):
    logger.info("Preview CSV start filename=%s", file.filename)
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="仅支持预览 .csv 文件")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="预览文件为空")

    import uuid

    safe_filename = f"preview_{uuid.uuid4().hex}.csv"
    target_path = UPLOAD_DIR / safe_filename
    target_path.write_bytes(content)

    try:
        preview_data = get_csv_preview(target_path)
        return {**preview_data, "file_path": str(target_path)}
    except Exception as exc:
        logger.exception("CSV preview failed path=%s", target_path)
        raise HTTPException(status_code=400, detail=f"CSV 预览失败: {exc}") from exc


@router.post("/collect")
def create_collect_job(payload: CollectJobCreate, db: Session = Depends(get_db)):
    logger.info("Create collect job: %s", payload.job_name)
    query_payload = {
        "queries": payload.queries,
        "time_window": payload.time_window,
        "source_type": payload.source_type,
    }
    if payload.file_path:
        query_payload["file_path"] = payload.file_path

    if "csv_import" not in payload.sources and not _has_valid_queries(payload.queries):
        raise HTTPException(status_code=400, detail="未提供有效查询条件")

    job = CollectJob(
        job_name=payload.job_name,
        sources=payload.sources,
        query_payload=query_payload,
        created_by=payload.created_by,
        dedup_strategy=payload.dedup_strategy,
        field_mapping=payload.field_mapping,
        auto_verify=payload.auto_verify,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    log_file = LOGS_DIR / f"{job.id}.log"
    log_file.write_text(
        f"{job.created_at.isoformat()} - INFO - Task created name={job.job_name} sources={job.sources}\n",
        encoding="utf-8",
    )

    if "sample" in payload.sources:
        result = import_sample_assets(db, job)
        return {"job_id": job.id, "status": job.status, **result}

    return {"job_id": job.id, "status": job.status}


@router.post("/{job_id}/rerun")
def rerun_job(job_id: str, db: Session = Depends(get_db)):
    original_job = _get_job_or_404(db, job_id)

    new_job_payload = CollectJobCreate(
        job_name=f"{original_job.job_name} (Rerun)",
        sources=original_job.sources,
        queries=(original_job.query_payload or {}).get("queries", []),
        file_path=(original_job.query_payload or {}).get("file_path"),
        source_type=(original_job.query_payload or {}).get("source_type"),
        created_by="rerun",
        dedup_strategy=original_job.dedup_strategy,
        field_mapping=original_job.field_mapping,
        auto_verify=original_job.auto_verify,
    )
    return create_collect_job(new_job_payload, db)


@router.post("/batch-delete", response_model=JobBatchOperationResponse)
def batch_delete_jobs(payload: JobBatchIdsRequest, db: Session = Depends(get_db)):
    ensure_job_pending_assets_schema(db)
    if not payload.ids:
        raise HTTPException(status_code=400, detail="ids is required")
    if len(payload.ids) > 100:
        raise HTTPException(status_code=400, detail="ids exceeds limit")

    items = []
    success = 0
    failed = 0
    for job_id in payload.ids:
        job = db.get(CollectJob, job_id)
        if not job:
            items.append({"id": job_id, "ok": False, "error": "Job not found"})
            failed += 1
            continue
        if not _job_can_delete(job):
            items.append({"id": job_id, "ok": False, "error": f"Job status {job.status} cannot be deleted"})
            failed += 1
            continue
        _pending_assets_query(db, job_id).delete(synchronize_session=False)
        db.delete(job)
        success += 1
        items.append({"id": job_id, "ok": True})
    db.commit()
    return {"total": len(payload.ids), "success": success, "failed": failed, "items": items}


@router.post("/batch-rerun", response_model=JobBatchOperationResponse)
def batch_rerun_jobs(payload: JobBatchIdsRequest, db: Session = Depends(get_db)):
    if not payload.ids:
        raise HTTPException(status_code=400, detail="ids is required")
    if len(payload.ids) > 100:
        raise HTTPException(status_code=400, detail="ids exceeds limit")

    items = []
    success = 0
    failed = 0
    for job_id in payload.ids:
        job = db.get(CollectJob, job_id)
        if not job:
            items.append({"id": job_id, "ok": False, "error": "Job not found"})
            failed += 1
            continue
        if not _job_can_rerun(job):
            items.append({"id": job_id, "ok": False, "error": f"Job status {job.status} cannot be rerun"})
            failed += 1
            continue
        new_job = create_collect_job(
            CollectJobCreate(
                job_name=f"{job.job_name} (Rerun)",
                sources=job.sources,
                queries=(job.query_payload or {}).get("queries", []),
                file_path=(job.query_payload or {}).get("file_path"),
                source_type=(job.query_payload or {}).get("source_type"),
                created_by="rerun",
                dedup_strategy=job.dedup_strategy,
                field_mapping=job.field_mapping,
                auto_verify=job.auto_verify,
            ),
            db,
        )
        success += 1
        items.append({"id": job_id, "ok": True, "new_job_id": new_job["job_id"]})
    return {"total": len(payload.ids), "success": success, "failed": failed, "items": items}


@router.post("/batch-start", response_model=JobBatchOperationResponse)
def batch_start_jobs(payload: JobBatchIdsRequest, db: Session = Depends(get_db)):
    if not payload.ids:
        raise HTTPException(status_code=400, detail="ids is required")
    if len(payload.ids) > 100:
        raise HTTPException(status_code=400, detail="ids exceeds limit")

    items = []
    success = 0
    failed = 0
    for job_id in payload.ids:
        job = db.get(CollectJob, job_id)
        if not job:
            items.append({"id": job_id, "ok": False, "error": "Job not found"})
            failed += 1
            continue
        if not _job_can_start(job):
            items.append({"id": job_id, "ok": False, "error": f"Job status {job.status} cannot be started"})
            failed += 1
            continue
        start_task(job_id, db)
        success += 1
        items.append({"id": job_id, "ok": True})
    return {"total": len(payload.ids), "success": success, "failed": failed, "items": items}


@router.post("/{job_id}/start")
def start_task(job_id: str, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    if job.status == "running":
        return {"message": "Job is already running", "job_id": job_id}

    job.status = "running"
    db.commit()

    from app.tasks.collect import run_collect_task

    run_in_process(run_collect_task, job_id, delay=1)
    return {"message": "Job started in background", "job_id": job_id}


@router.post("/{job_id}/stop")
def stop_task(job_id: str, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    job.status = "cancelled"
    db.commit()
    return {"message": "Job cancellation requested", "job_id": job_id}


@router.get("/{job_id}/status")
def get_task_status(job_id: str, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)

    return {
        "id": job.id,
        "status": job.status,
        "progress": job.progress,
        "success_count": job.success_count,
        "failed_count": job.failed_count,
        "duplicate_count": job.duplicate_count,
        "total_count": job.total_count,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "error_message": job.error_message,
    }
