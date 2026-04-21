import asyncio
import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlsplit

import httpx
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.config import BASE_DIR
from app.core.db import SessionLocal
from app.core.huey import huey, run_in_process
from app.models import CollectJob, Host, Service, SourceObservation, WebEndpoint
from app.models.support import Screenshot
from app.services.collectors import get_collector
from app.services.collectors.base import BaseCollector
from app.services.collectors.dedup import touch_existing_web_endpoint
from app.services.collectors.fofa_csv import parse_fofa_csv
from app.services.collectors.hunter_csv import parse_hunter_csv
from app.services.collectors.mapped_csv import parse_mapped_csv
from app.services.collectors.quake_csv import parse_quake_csv
from app.services.collectors.zoomeye_csv import parse_zoomeye_csv
from app.services.normalizer.service import build_url_hash, normalize_url
from app.services.system_service import SystemConfigService

logger = logging.getLogger(__name__)
CSV_SOURCE_PARSERS = {
    "fofa": parse_fofa_csv,
    "hunter": parse_hunter_csv,
    "zoomeye": parse_zoomeye_csv,
    "quake": parse_quake_csv,
}


class _JobFileHandlerFilter(logging.Filter):
    def __init__(self, job_id: str):
        super().__init__()
        self.job_id = str(job_id)

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - tiny predicate
        return getattr(record, "job_id", None) == self.job_id


class JobLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra = kwargs.get("extra") or {}
        extra["job_id"] = self.extra["job_id"]
        kwargs["extra"] = extra
        return msg, kwargs


class SaveAssetsResult:
    def __init__(self):
        self.success_count = 0
        self.duplicate_count = 0
        self.failed_count = 0


class PostProcessResult:
    def __init__(self):
        self.verified_success = 0
        self.verified_failed = 0
        self.screenshot_success = 0
        self.screenshot_failed = 0


def _desensitize_headers(headers: Dict[str, Any] | None) -> Dict[str, Any]:
    if not headers:
        return {}
    sanitized: Dict[str, Any] = {}
    for key, value in headers.items():
        key_lower = str(key).lower()
        if any(token in key_lower for token in ("key", "token", "authorization", "secret", "password")):
            masked = ""
            if value is not None:
                value_str = str(value)
                if len(value_str) >= 6:
                    masked = f"{value_str[:3]}***{value_str[-2:]}"
                elif value_str:
                    masked = "***"
            sanitized[key] = masked
        else:
            sanitized[key] = value
    return sanitized


def _desensitize_url(url: str) -> str:
    if not url:
        return ""
    safe = url
    for marker in ("api-key=", "api_key=", "key=", "token=", "authorization="):
        idx = safe.lower().find(marker)
        if idx == -1:
            continue
        start = idx + len(marker)
        end = safe.find("&", start)
        if end == -1:
            safe = f"{safe[:start]}***"
        else:
            safe = f"{safe[:start]}***{safe[end:]}"
    return safe


def _add_http_trace_hooks(client: httpx.AsyncClient, job_logger: JobLoggerAdapter, source_name: str) -> None:
    if not hasattr(client, "event_hooks"):
        return

    async def on_request(request: httpx.Request):
        job_logger.info(
            "[%s] HTTP %s %s headers=%s",
            source_name,
            request.method,
            _desensitize_url(str(request.url)),
            _desensitize_headers(dict(request.headers)),
        )

    async def on_response(response: httpx.Response):
        req = response.request
        body_preview = ""
        try:
            payload = response.json()
            if isinstance(payload, dict):
                body_preview = str(
                    {
                        "code": payload.get("code"),
                        "message": payload.get("message") or payload.get("msg"),
                        "error": payload.get("error"),
                    }
                )
            else:
                body_preview = str(payload)[:160]
        except Exception:
            try:
                body_preview = response.text[:160]
            except Exception:
                body_preview = ""

        job_logger.info(
            "[%s] HTTP %s %s -> %s %s",
            source_name,
            req.method,
            _desensitize_url(str(req.url)),
            response.status_code,
            body_preview,
        )

    hooks = client.event_hooks
    hooks.setdefault("request", []).append(on_request)
    hooks.setdefault("response", []).append(on_response)


def _bind_http_trace_on_collector(collector: Any, job_logger: JobLoggerAdapter, source_name: str):
    original_ac = httpx.AsyncClient

    def _wrapped_async_client(*args, **kwargs):
        client = original_ac(*args, **kwargs)
        _add_http_trace_hooks(client, job_logger, source_name)
        return client

    targets = []
    module_obj = None
    try:
        module_obj = __import__(collector.__class__.__module__, fromlist=["httpx"])
    except Exception:
        module_obj = None

    if module_obj is not None and getattr(module_obj, "httpx", None) is httpx:
        targets.append(module_obj)

    current_mod = __import__(__name__, fromlist=["httpx"])
    if current_mod is not None and getattr(current_mod, "httpx", None) is httpx:
        targets.append(current_mod)

    previous = []
    for module in targets:
        previous.append((module, module.httpx.AsyncClient))
        module.httpx.AsyncClient = _wrapped_async_client

    def restore():
        for module, old_client in previous:
            module.httpx.AsyncClient = old_client

    return restore


def get_current_thread_event_loop():
    policy = asyncio.get_event_loop_policy()
    local_state = getattr(policy, "_local", None)
    if local_state is None:
        return None
    return getattr(local_state, "_loop", None)


def run_coro_in_fresh_loop(coro):
    previous_loop = get_current_thread_event_loop()
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        asyncio.set_event_loop(previous_loop)
        loop.close()


def run_collector_query(
    collector,
    query_str: str,
    query_payload: dict,
    config: dict,
    *,
    source_name: str | None = None,
    job_logger: JobLoggerAdapter | None = None,
):
    restore_httpx = None
    payload = dict(query_payload or {})
    if job_logger is not None:
        payload["_job_logger"] = job_logger
    if source_name and job_logger is not None:
        restore_httpx = _bind_http_trace_on_collector(collector, job_logger, source_name)

    try:
        return run_coro_in_fresh_loop(collector.run(query_str, payload, config))
    finally:
        if restore_httpx is not None:
            restore_httpx()


def _open_job_logger(job_id: str, *, mode: str) -> tuple[logging.Logger, logging.FileHandler, JobLoggerAdapter]:
    logs_dir = BASE_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / f"{job_id}.log"
    task_logger = logging.getLogger()
    file_handler = logging.FileHandler(log_file, mode=mode, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    file_handler.addFilter(_JobFileHandlerFilter(job_id))
    task_logger.addHandler(file_handler)
    return task_logger, file_handler, JobLoggerAdapter(logger, {"job_id": job_id})


def _close_job_logger(task_logger: logging.Logger, file_handler: logging.FileHandler) -> None:
    task_logger.removeHandler(file_handler)
    file_handler.close()


async def _verify_assets_for_post_process(assets: list[WebEndpoint]) -> dict[str, tuple[int | None, str | None]]:
    if not assets:
        return {}

    from app.api.assets import fetch_status_code_with_playwright
    from playwright.async_api import async_playwright

    results: dict[str, tuple[int | None, str | None]] = {}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(ignore_https_errors=True)
        try:
            for asset in assets:
                results[asset.id] = await fetch_status_code_with_playwright(context, asset.normalized_url)
        finally:
            await context.close()
            await browser.close()
    return results


def load_job(db: Session, job_id: str):
    return db.query(CollectJob).filter(CollectJob.id == job_id).first()


def is_job_cancelled(db: Session, job_id: str) -> bool:
    current = load_job(db, job_id)
    return bool(current and current.status == "cancelled")


def finish_cancelled_job(job: CollectJob, db: Session, *, job_logger: JobLoggerAdapter | None = None) -> None:
    job.status = "cancelled"
    job.finished_at = datetime.utcnow()
    db.commit()
    if job_logger is not None:
        job_logger.info("Task cancelled")


def _safe_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_protocol(value: Any, *, default: str = "https") -> str:
    text = _safe_text(value)
    if not text:
        return default
    lowered = text.lower()
    aliases = {
        "ssl/http": "https",
        "ssl": "https",
        "tls": "https",
        "https": "https",
        "http": "http",
        "https?": "https",
        "udp": "udp",
        "tcp": "tcp",
    }
    if lowered in aliases:
        return aliases[lowered]
    if lowered.startswith("https"):
        return "https"
    if lowered.startswith("http"):
        return "http"
    return lowered


def _normalize_company(value: Any) -> str | None:
    return _safe_text(value)


def _safe_port(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _build_url_from_asset(asset_data: dict[str, Any]) -> str | None:
    protocol = _normalize_protocol(asset_data.get("protocol"), default="https")
    if _is_non_web_protocol(protocol):
        return None

    return BaseCollector.build_url(
        url=_safe_text(asset_data.get("url")),
        host=(
            _safe_text(asset_data.get("host"))
            or _safe_text(asset_data.get("subdomain"))
            or _safe_text(asset_data.get("domain"))
        ),
        ip=_safe_text(asset_data.get("ip")),
        port=_safe_port(asset_data.get("port")),
        protocol=protocol,
    )


def _extract_host_from_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parts = urlsplit(url if url.startswith(("http://", "https://")) else f"https://{url}")
    except Exception:
        return None
    return parts.hostname or None


def _is_non_web_protocol(protocol: str | None) -> bool:
    return protocol not in {None, "", "http", "https"}


def _guess_web_protocol(protocol: str | None, port: int | None) -> str:
    normalized = _normalize_protocol(protocol, default="")
    if normalized in {"http", "https"}:
        return normalized
    if port in {443, 8443}:
        return "https"
    if port in {80, 8080, 8000}:
        return "http"
    return "https"


def _build_fallback_endpoint_url(*, protocol: str | None, host: str | None, ip: str | None, port: int | None) -> str | None:
    if _is_non_web_protocol(protocol):
        return None

    target = host or ip
    if not target:
        return None

    scheme = _guess_web_protocol(protocol, port)
    effective_port = port if port is not None else (443 if scheme == "https" else 80 if scheme == "http" else None)
    if effective_port and not ((scheme == "http" and effective_port == 80) or (scheme == "https" and effective_port == 443)):
        return f"{scheme}://{target}:{effective_port}"
    return f"{scheme}://{target}"


def _looks_like_ip(value: str | None) -> bool:
    if not value:
        return False
    parts = value.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(part) <= 255 for part in parts)
    except ValueError:
        return False


def _build_asset_identity_key(resolved: dict[str, Any], source_name: str) -> str | None:
    normalized_url = _safe_text(resolved.get("normalized_url"))
    if normalized_url:
        return f"url:{normalized_url}"

    domain = _safe_text(resolved.get("domain"))
    host = _safe_text(resolved.get("host"))
    ip = _safe_text(resolved.get("ip"))
    if host and _looks_like_ip(host):
        ip = ip or host
        host = None
    port = resolved.get("port")

    if domain and port is not None:
        return f"domain-port:{domain}:{port}"
    if host and port is not None:
        return f"host-port:{host}:{port}"
    if ip and port is not None:
        return f"ip-port:{ip}:{port}"
    if domain:
        return f"domain:{domain}"
    if host:
        return f"host:{host}"
    if ip:
        return f"ip:{ip}"

    source_hint = _safe_text(source_name)
    title = _safe_text(resolved.get("title"))
    if source_hint and title:
        return f"source-title:{source_hint}:{title}"
    return None


def _build_source_record_id(source_name: str, resolved: dict[str, Any]) -> str | None:
    identity_key = _build_asset_identity_key(resolved, source_name)
    if identity_key:
        return f"{source_name}:{identity_key}"
    return None


def _serialize_observation_payload(asset_data: Dict[str, Any], resolved: dict[str, Any], source_name: str, web: WebEndpoint | None) -> dict[str, Any]:
    raw_payload = dict(asset_data.get("raw_data") or {})
    if web is not None and getattr(web, "id", None):
        raw_payload["web_endpoint_id"] = getattr(web, "id")

    normalized_url = _safe_text(resolved.get("normalized_url"))
    fallback_url = _safe_text(resolved.get("fallback_url"))
    raw_payload.update(
        {
            "source": source_name,
            "url": _safe_text(asset_data.get("url")) or normalized_url or fallback_url,
            "normalized_url": normalized_url,
            "fallback_url": fallback_url,
            "resolved_host": resolved.get("host"),
            "resolved_ip": resolved.get("ip"),
            "resolved_domain": resolved.get("domain"),
            "resolved_port": resolved.get("port"),
            "resolved_protocol": resolved.get("protocol"),
            "asset_identity_key": _build_asset_identity_key(resolved, source_name),
            "source_record_id": _build_source_record_id(source_name, resolved),
        }
    )
    return raw_payload


def _upsert_source_observation(
    asset_db: Session,
    job: CollectJob,
    source_name: str,
    observed_at: datetime,
    source_record_id: str | None,
    raw_payload: dict[str, Any],
) -> None:
    asset_db.add(
        SourceObservation(
            collect_job_id=job.id,
            source_name=source_name,
            source_record_id=source_record_id,
            raw_payload=raw_payload,
            observed_at=observed_at,
        )
    )


def _resolve_asset_identity(asset_data: dict[str, Any]) -> dict[str, Any]:
    ip = _safe_text(asset_data.get("ip"))
    domain = _safe_text(asset_data.get("domain"))
    host = _safe_text(asset_data.get("host")) or _safe_text(asset_data.get("subdomain"))
    title = _safe_text(asset_data.get("title"))
    protocol = _normalize_protocol(asset_data.get("protocol"), default="https")
    port = _safe_port(asset_data.get("port"))
    direct_url = _build_url_from_asset(asset_data)
    parsed_host = _extract_host_from_url(direct_url)

    if not host:
        host = parsed_host or domain or ip
    if not domain and parsed_host and not _looks_like_ip(parsed_host):
        domain = parsed_host
    if not ip and parsed_host and _looks_like_ip(parsed_host):
        ip = parsed_host
    if not domain and host and not _looks_like_ip(host):
        domain = host
    if not ip and host and _looks_like_ip(host):
        ip = host

    web_protocol = None if _is_non_web_protocol(protocol) else _guess_web_protocol(protocol, port)
    if port is None and web_protocol is not None:
        port = 443 if web_protocol == "https" else 80 if web_protocol == "http" else None

    fallback_url = _build_fallback_endpoint_url(
        protocol=protocol,
        host=host or domain,
        ip=ip,
        port=port,
    )
    normalized_url = normalize_url(direct_url or fallback_url) if (direct_url or fallback_url) else None

    return {
        "ip": ip,
        "domain": domain,
        "host": host,
        "title": title,
        "protocol": web_protocol or protocol,
        "port": port,
        "url": direct_url,
        "normalized_url": normalized_url,
        "fallback_url": fallback_url,
        "company": _normalize_company(asset_data.get("org") or asset_data.get("company")),
        "server": _safe_text(asset_data.get("server")),
        "country": _safe_text(asset_data.get("country")),
        "city": _safe_text(asset_data.get("city")),
        "status_code": asset_data.get("status_code"),
    }


def _ensure_saveable_identity(asset_data: dict[str, Any], source_name: str) -> dict[str, Any] | None:
    resolved = _resolve_asset_identity(asset_data)
    has_identity = any(
        [
            resolved.get("normalized_url"),
            resolved.get("fallback_url"),
            resolved.get("domain"),
            resolved.get("host"),
            resolved.get("ip"),
        ]
    )
    if not has_identity:
        return None

    protocol_default = "http" if source_name == "oneforall" else "https"
    if _is_non_web_protocol(resolved.get("protocol")):
        resolved["primary_url"] = None
        return resolved

    resolved["protocol"] = _normalize_protocol(
        resolved.get("protocol"),
        default=protocol_default,
    )
    if resolved.get("port") is None:
        resolved["port"] = 443 if resolved.get("protocol") == "https" else 80 if resolved.get("protocol") == "http" else None
    resolved["primary_url"] = resolved.get("normalized_url") or resolved.get("fallback_url")
    return resolved


def _find_existing_web_endpoint(asset_db: Session, resolved: dict[str, Any]) -> WebEndpoint | None:
    normalized_url = _safe_text(resolved.get("normalized_url"))
    if normalized_url:
        url_hash = build_url_hash(normalized_url)
        existing = asset_db.query(WebEndpoint).filter(WebEndpoint.normalized_url_hash == url_hash).first()
        if existing:
            return existing

    domain = _safe_text(resolved.get("domain"))
    port = resolved.get("port")
    if domain:
        scoped = asset_db.query(WebEndpoint).filter(WebEndpoint.domain == domain)
        if port is not None:
            scoped = scoped.join(Service, WebEndpoint.service_id == Service.id).filter(Service.port == port)
        existing = scoped.order_by(WebEndpoint.last_seen_at.desc().nullslast()).first()
        if existing:
            return existing

    ip = _safe_text(resolved.get("ip"))
    if ip and port is not None:
        existing = (
            asset_db.query(WebEndpoint)
            .join(Host, WebEndpoint.host_id == Host.id)
            .join(Service, WebEndpoint.service_id == Service.id)
            .filter(and_(Host.ip == ip, Service.port == port))
            .order_by(WebEndpoint.last_seen_at.desc().nullslast())
            .first()
        )
        if existing:
            return existing

    return None


def _save_asset_row_with_session(
    asset_db: Session,
    job: CollectJob,
    asset_data: Dict[str, Any],
    source_name: str,
    index: int,
    logger_ref,
) -> tuple[int, int, int]:
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
        return (0, 0, 1)

    observed_at = datetime.utcnow()
    normalized_url = _safe_text(resolved.get("normalized_url"))
    fallback_url = _safe_text(resolved.get("fallback_url"))
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

        source_meta = dict(getattr(existing_web, "source_meta", {}) or {})
        source_meta.update(
            {
                "source": source_name,
                "import_job_id": job.id,
                "raw": asset_data.get("raw_data"),
                "asset_identity_key": identity_key,
                "source_record_id": source_record_id,
                "domain": resolved.get("domain"),
                "host": resolved.get("host"),
                "ip": resolved.get("ip"),
                "port": resolved.get("port"),
            }
        )
        existing_web.source_meta = source_meta
        web = existing_web
        duplicate = 1
        success = 0
        logger_ref.info(
            "[%s] save duplicate row=%s key=%s url=%s fallback=%s",
            source_name,
            index,
            identity_key,
            normalized_url,
            fallback_url,
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
            source_meta={
                "source": source_name,
                "import_job_id": job.id,
                "raw": asset_data.get("raw_data"),
                "asset_identity_key": identity_key,
                "source_record_id": source_record_id,
                "domain": resolved.get("domain"),
                "host": resolved.get("host"),
                "ip": resolved.get("ip"),
                "port": resolved.get("port"),
            },
        )
        asset_db.add(web)
        if hasattr(asset_db, "flush"):
            asset_db.flush()
        duplicate = 0
        success = 1
        logger_ref.info(
            "[%s] save success row=%s key=%s url=%s",
            source_name,
            index,
            identity_key,
            normalized_url,
        )
    else:
        web = None
        duplicate = 0
        success = 1
        logger_ref.info(
            "[%s] save observation-only row=%s key=%s host=%s ip=%s port=%s",
            source_name,
            index,
            identity_key,
            resolved.get("host"),
            resolved.get("ip"),
            resolved.get("port"),
        )

    raw_payload = _serialize_observation_payload(asset_data, resolved, source_name, web)
    _upsert_source_observation(asset_db, job, source_name, observed_at, source_record_id, raw_payload)
    if hasattr(asset_db, "flush"):
        asset_db.flush()
    return (success, duplicate, 0)


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
    job_logger: JobLoggerAdapter | None = None,
) -> SaveAssetsResult:
    result = SaveAssetsResult()
    logger_ref = job_logger or logger

    for index, asset_data in enumerate(assets, start=1):
        isolated_session = _create_isolated_asset_session() if hasattr(db, "bind") else None
        asset_db = isolated_session or db
        try:
            success, duplicate, failed = _save_asset_row_with_session(
                asset_db,
                job,
                asset_data,
                source_name,
                index,
                logger_ref,
            )
            if hasattr(asset_db, "commit"):
                asset_db.commit()
            result.success_count += success
            result.duplicate_count += duplicate
            result.failed_count += failed
        except Exception as exc:
            if hasattr(asset_db, "rollback"):
                asset_db.rollback()
            result.failed_count += 1
            logger_ref.exception("[%s] save failed row=%s reason=%s", source_name, index, exc)
        finally:
            if isolated_session is not None:
                isolated_session.close()

    if hasattr(db, "refresh"):
        db.refresh(job)

    job.success_count = int(getattr(job, "success_count", 0) or 0) + result.success_count
    job.duplicate_count = int(getattr(job, "duplicate_count", 0) or 0) + result.duplicate_count
    job.failed_count = int(getattr(job, "failed_count", 0) or 0) + result.failed_count
    job.total_count = int(job.success_count) + int(job.failed_count) + int(job.duplicate_count)
    db.commit()

    logger_ref.info(
        "[%s] save summary success=%s duplicate=%s failed=%s total=%s",
        source_name,
        result.success_count,
        result.duplicate_count,
        result.failed_count,
        job.total_count,
    )
    return result


def _save_assets_bridge(
    db: Session,
    job: CollectJob,
    assets: List[Dict[str, Any]],
    source_name: str,
    job_logger: JobLoggerAdapter | None,
):
    if job_logger is None:
        return save_assets(db, job, assets, source_name)
    try:
        return save_assets(db, job, assets, source_name, job_logger=job_logger)
    except TypeError as exc:
        if "job_logger" in str(exc):
            return save_assets(db, job, assets, source_name)
        raise


def _prepare_import_records(records: list[dict]) -> list[dict]:
    prepared: list[dict] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        item = dict(record)
        if "raw_data" not in item or item.get("raw_data") is None:
            item["raw_data"] = dict(record)
        prepared.append(item)
    return prepared


def _count_csv_rows(file_path: str | Path) -> int:
    path = Path(file_path)
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            return sum(1 for _ in reader)
    except Exception:
        return 0


def process_csv_import_job(db: Session, job: CollectJob, *, job_logger: JobLoggerAdapter | None = None) -> None:
    payload = job.query_payload or {}
    file_path = payload.get("file_path")
    if not file_path:
        raise ValueError("csv_import job is missing file_path")

    source_type = str(payload.get("source_type") or "").strip().lower()
    logger_ref = job_logger or logger
    logger_ref.info("CSV import start source_type=%s file=%s", source_type or "mapped", file_path)

    parser = CSV_SOURCE_PARSERS.get(source_type)
    if parser is not None:
        records = _prepare_import_records(parser(file_path))
        failed_rows = 0
        parser_name = source_type
        save_source = "csv_import"
        logger_ref.info("CSV vendor parser used source=%s records=%s", source_type, len(records))
    else:
        mapped_result = parse_mapped_csv(file_path, job.field_mapping or {})
        records = _prepare_import_records(mapped_result.records)
        failed_rows = mapped_result.failed_rows
        parser_name = "mapped"
        save_source = "csv_import"
        logger_ref.info(
            "CSV mapped parser used records=%s failed_rows=%s source_hint=%s",
            len(records),
            failed_rows,
            source_type or "auto",
        )

    _save_assets_bridge(db, job, records, save_source, job_logger)

    job.failed_count = int(getattr(job, "failed_count", 0) or 0) + failed_rows

    total_rows = _count_csv_rows(file_path)
    if total_rows <= 0:
        total_rows = len(records) + failed_rows
    computed_total = max(total_rows, int(job.success_count) + int(job.duplicate_count) + int(job.failed_count))
    job.total_count = computed_total
    job.progress = 100
    db.commit()

    logger_ref.info(
        "CSV import finished parser=%s source=%s total=%s success=%s duplicate=%s failed=%s parser_failed=%s",
        parser_name,
        save_source,
        job.total_count,
        int(job.success_count),
        int(job.duplicate_count),
        int(job.failed_count),
        failed_rows,
    )


def _is_valid_query_item(query_item: dict[str, Any] | None) -> bool:
    if not isinstance(query_item, dict):
        return False
    source = str(query_item.get("source") or "").strip()
    query = str(query_item.get("query") or "").strip()
    return bool(source and query)


def _valid_query_items(queries: list[dict] | None) -> list[dict[str, Any]]:
    if not isinstance(queries, list):
        return []
    return [item for item in queries if _is_valid_query_item(item)]




def _build_asset_lookup_indexes(assets: list[WebEndpoint]) -> dict[str, dict[Any, WebEndpoint]]:
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
        by_id[getattr(asset, "id", None)] = asset

        raw_url = _safe_text(getattr(asset, "normalized_url", None))
        if raw_url:
            by_url[raw_url] = asset
            try:
                by_url[normalize_url(raw_url)] = asset
            except Exception:
                pass

        source_meta = getattr(asset, "source_meta", {}) or {}
        identity_key = _safe_text(source_meta.get("asset_identity_key"))
        if identity_key:
            by_identity[identity_key] = asset
        source_record_id = _safe_text(source_meta.get("source_record_id"))
        if source_record_id:
            by_source_record[source_record_id] = asset

        service = getattr(asset, "service", None)
        host_obj = getattr(service, "host", None) if service else getattr(asset, "host", None)
        domain = _safe_text(getattr(asset, "domain", None) or source_meta.get("domain"))
        ip = _safe_text((getattr(host_obj, "ip", None) if host_obj else None) or source_meta.get("ip"))
        port = getattr(service, "port", None) if service else source_meta.get("port")
        port = _safe_port(port)
        host = _safe_text(source_meta.get("host") or source_meta.get("subdomain") or domain or ip)

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


def _resolve_asset_id_from_payload(raw_payload: dict[str, Any], indexes: dict[str, dict[Any, WebEndpoint]], source_record_id: str | None = None) -> str | None:
    web_id = raw_payload.get("web_endpoint_id") or raw_payload.get("id")
    if web_id:
        asset = indexes["by_id"].get(web_id)
        if asset is not None and getattr(asset, "id", None):
            return asset.id

    source_record_value = _safe_text(source_record_id or raw_payload.get("source_record_id"))
    if source_record_value:
        asset = indexes["by_source_record"].get(source_record_value)
        if asset is not None and getattr(asset, "id", None):
            return asset.id

    normalized_url = _safe_text(
        raw_payload.get("normalized_url") or raw_payload.get("fallback_url") or raw_payload.get("url")
    )
    if normalized_url:
        asset = indexes["by_url"].get(normalized_url)
        if asset is None:
            try:
                asset = indexes["by_url"].get(normalize_url(normalized_url))
            except Exception:
                asset = None
        if asset is not None and getattr(asset, "id", None):
            return asset.id

    identity_key = _safe_text(raw_payload.get("asset_identity_key"))
    if identity_key:
        asset = indexes["by_identity"].get(identity_key)
        if asset is not None and getattr(asset, "id", None):
            return asset.id

    domain = _safe_text(raw_payload.get("resolved_domain") or raw_payload.get("domain"))
    host = _safe_text(raw_payload.get("resolved_host") or raw_payload.get("host"))
    ip = _safe_text(raw_payload.get("resolved_ip") or raw_payload.get("ip"))
    port = _safe_port(raw_payload.get("resolved_port") or raw_payload.get("port"))

    candidate = None
    if domain and port is not None:
        candidate = indexes["by_domain_port"].get((domain, port))
    if candidate is None and host and port is not None:
        candidate = indexes["by_host_port"].get((host, port))
    if candidate is None and ip and port is not None:
        candidate = indexes["by_ip_port"].get((ip, port))
    if candidate is None and domain:
        candidate = indexes["by_domain"].get(domain)
    if candidate is None and host:
        candidate = indexes["by_host"].get(host)
    if candidate is None and ip:
        candidate = indexes["by_ip"].get(ip)
    if candidate is not None and getattr(candidate, "id", None):
        return candidate.id
    return None


def _build_observation_asset_query(db: Session, observations: list[SourceObservation]):
    ids: set[str] = set()
    source_record_ids: set[str] = set()
    urls: set[str] = set()
    identity_keys: set[str] = set()
    domains: set[str] = set()
    hosts: set[str] = set()
    ips: set[str] = set()

    for obs in observations:
        raw_payload = obs.raw_payload or {}
        if raw_payload.get("web_endpoint_id"):
            ids.add(str(raw_payload.get("web_endpoint_id")))
        if getattr(obs, "source_record_id", None) or raw_payload.get("source_record_id"):
            source_record_ids.add(str(getattr(obs, "source_record_id", None) or raw_payload.get("source_record_id")))
        normalized_url = _safe_text(raw_payload.get("normalized_url") or raw_payload.get("fallback_url") or raw_payload.get("url"))
        if normalized_url:
            try:
                urls.add(normalize_url(normalized_url))
            except Exception:
                urls.add(normalized_url)
        if raw_payload.get("asset_identity_key"):
            identity_keys.add(str(raw_payload.get("asset_identity_key")))
        if raw_payload.get("resolved_domain") or raw_payload.get("domain"):
            domains.add(str(raw_payload.get("resolved_domain") or raw_payload.get("domain")))
        if raw_payload.get("resolved_host") or raw_payload.get("host"):
            hosts.add(str(raw_payload.get("resolved_host") or raw_payload.get("host")))
        if raw_payload.get("resolved_ip") or raw_payload.get("ip"):
            ips.add(str(raw_payload.get("resolved_ip") or raw_payload.get("ip")))

    filters = []
    if ids:
        filters.append(WebEndpoint.id.in_(sorted(ids)))
    if urls:
        filters.append(WebEndpoint.normalized_url.in_(sorted(urls)))
    if domains:
        filters.append(WebEndpoint.domain.in_(sorted(domains)))
    if source_record_ids:
        filters.append(WebEndpoint.source_meta["source_record_id"].astext.in_(sorted(source_record_ids)))
    if identity_keys:
        filters.append(WebEndpoint.source_meta["asset_identity_key"].astext.in_(sorted(identity_keys)))
    if hosts:
        filters.append(WebEndpoint.source_meta["host"].astext.in_(sorted(hosts)))
        filters.append(WebEndpoint.source_meta["subdomain"].astext.in_(sorted(hosts)))
    if ips:
        filters.append(WebEndpoint.source_meta["ip"].astext.in_(sorted(ips)))

    query = db.query(WebEndpoint)
    if filters:
        return query.filter(or_(*filters))
    return query.filter(WebEndpoint.id.in_([]))

def _collect_job_asset_ids(db: Session, job_id: str) -> list[str]:
    observations = (
        db.query(SourceObservation)
        .filter(SourceObservation.collect_job_id == job_id)
        .order_by(SourceObservation.created_at.desc())
        .all()
    )
    if not observations:
        return []

    assets = _build_observation_asset_query(db, observations).all()
    indexes = _build_asset_lookup_indexes(assets)
    asset_ids: list[str] = []
    seen: set[str] = set()
    for obs in observations:
        raw_payload = obs.raw_payload or {}
        asset_id = _resolve_asset_id_from_payload(raw_payload, indexes, getattr(obs, "source_record_id", None))
        if not asset_id or asset_id in seen:
            continue
        seen.add(asset_id)
        asset_ids.append(asset_id)
    return asset_ids



def _determine_job_status(job: CollectJob, source_errors: list[str], *, executed_queries: int) -> str:
    success_count = int(getattr(job, "success_count", 0) or 0)
    duplicate_count = int(getattr(job, "duplicate_count", 0) or 0)
    failed_count = int(getattr(job, "failed_count", 0) or 0)
    completed_items = success_count + duplicate_count

    if job.status == "cancelled":
        return "cancelled"
    if executed_queries == 0:
        return "failed"
    if completed_items > 0 and (failed_count > 0 or source_errors):
        return "partial_success"
    if completed_items > 0:
        return "success"
    if failed_count > 0 or source_errors:
        return "failed"
    return "success"


@huey.task()
def run_collect_task(job_id: str):
    task_logger, file_handler, job_logger = _open_job_logger(job_id, mode="a")

    db: Session = SessionLocal()
    job = load_job(db, job_id)
    if not job:
        db.close()
        task_logger.removeHandler(file_handler)
        file_handler.close()
        return

    for field in ("success_count", "failed_count", "duplicate_count", "total_count"):
        if getattr(job, field, None) is None:
            setattr(job, field, 0)

    source_errors: list[str] = []
    executed_queries = 0
    try:
        job_name = getattr(job, "job_name", "")
        sources_for_log = getattr(job, "sources", [])
        job_logger.info("Task created job_id=%s name=%s sources=%s", job.id, job_name, sources_for_log)
        job.status = "running"
        job.started_at = datetime.utcnow()
        job.progress = 0
        db.commit()
        job_logger.info("Task started")

        if is_job_cancelled(db, job_id):
            finish_cancelled_job(job, db, job_logger=job_logger)
            job_logger.info("Task cancelled before execution")
            return

        sources = getattr(job, "sources", []) or []
        query_payload = getattr(job, "query_payload", {}) or {}
        if "csv_import" in sources:
            executed_queries = 1
            process_csv_import_job(db, job, job_logger=job_logger)
            if is_job_cancelled(db, job_id):
                finish_cancelled_job(job, db, job_logger=job_logger)
                job_logger.info("Task cancelled after csv import")
                return
        else:
            queries = query_payload.get("queries", [])
            valid_queries = _valid_query_items(queries)
            if not valid_queries:
                job.status = "failed"
                job.progress = 100
                job.finished_at = datetime.utcnow()
                job.error_message = "未提供有效查询条件"
                db.commit()
                job_logger.warning("Task failed reason=no-valid-queries")
                return

            total_queries = len(valid_queries)
            for index, q_item in enumerate(valid_queries, start=1):
                src_name = str(q_item.get("source") or "").strip()
                query_str = str(q_item.get("query") or "").strip()

                if is_job_cancelled(db, job_id):
                    finish_cancelled_job(job, db, job_logger=job_logger)
                    job_logger.info("Task cancelled during source loop")
                    return

                executed_queries += 1
                job_logger.info("Source start source=%s query=%s", src_name, query_str)
                try:
                    collector = get_collector(src_name)
                    config = SystemConfigService.get_decrypted_configs(db, src_name)
                    assets = run_collector_query(
                        collector,
                        query_str,
                        q_item,
                        config,
                        source_name=src_name,
                        job_logger=job_logger,
                    )
                    job_logger.info("Source fetched source=%s assets=%s", src_name, len(assets))

                    if is_job_cancelled(db, job_id):
                        finish_cancelled_job(job, db, job_logger=job_logger)
                        job_logger.info("Task cancelled after source fetch source=%s", src_name)
                        return

                    _save_assets_bridge(db, job, assets, src_name, job_logger)
                    job.total_count = int(job.success_count) + int(job.failed_count) + int(job.duplicate_count)
                    job.progress = int(index / total_queries * 100)
                    db.commit()
                    job_logger.info(
                        "Source saved source=%s progress=%s success=%s duplicate=%s failed=%s",
                        src_name,
                        job.progress,
                        job.success_count,
                        job.duplicate_count,
                        job.failed_count,
                    )

                    if is_job_cancelled(db, job_id):
                        finish_cancelled_job(job, db, job_logger=job_logger)
                        job_logger.info("Task cancelled after source save source=%s", src_name)
                        return
                except Exception as exc:
                    job_logger.exception("Collector %s failed", src_name)
                    source_errors.append(f"{src_name} failed: {exc}")
                    job.error_message = " | ".join(source_errors)
                    db.commit()

        if is_job_cancelled(db, job_id):
            finish_cancelled_job(job, db, job_logger=job_logger)
            job_logger.info("Task cancelled before finalize")
            return

        if executed_queries == 0 and "csv_import" not in sources:
            source_errors.append("没有可执行的有效采集查询")
            job.error_message = " | ".join(source_errors)

        job.status = _determine_job_status(job, source_errors, executed_queries=executed_queries)
        job.progress = 100
        job.finished_at = datetime.utcnow()
        job.total_count = int(job.success_count) + int(job.failed_count) + int(job.duplicate_count)
        job.error_message = " | ".join(source_errors) or None
        db.commit()

        job_logger.info(
            "Task finished status=%s success=%s duplicate=%s failed=%s total=%s",
            job.status,
            job.success_count,
            job.duplicate_count,
            job.failed_count,
            job.total_count,
        )

        if bool(getattr(job, "auto_verify", False)) and job.status in {"success", "partial_success"} and not is_job_cancelled(db, job.id):
            job_logger.info("Triggering auto verification and post-process")
            run_in_process(run_auto_post_process, job.id, delay=2)

    except Exception as exc:
        job_logger.exception("Task failed")
        job.status = "failed"
        job.finished_at = datetime.utcnow()
        job.error_message = str(exc)
        db.commit()
    finally:
        _close_job_logger(task_logger, file_handler)
        db.close()


@huey.task()
def run_auto_post_process(job_id: str):
    db: Session = SessionLocal()
    task_logger, file_handler, job_logger = _open_job_logger(job_id, mode="a")
    result = PostProcessResult()
    try:
        job = load_job(db, job_id)
        if not job or job.status == "cancelled":
            return

        target_ids = _collect_job_asset_ids(db, job_id)
        if not target_ids:
            job_logger.info("Auto verify skipped: no collected assets")
            return

        target_assets = db.query(WebEndpoint).filter(WebEndpoint.id.in_(target_ids)).all()
        assets_by_id = {asset.id: asset for asset in target_assets}
        ordered_assets = [assets_by_id[asset_id] for asset_id in target_ids if asset_id in assets_by_id]
        if not ordered_assets:
            job_logger.info("Auto verify skipped: no matched assets in database")
            return

        if is_job_cancelled(db, job_id):
            return

        job_logger.info("Auto verify start assets=%s", len(ordered_assets))
        try:
            verify_results = run_coro_in_fresh_loop(_verify_assets_for_post_process(ordered_assets))
            for asset in ordered_assets:
                status_code, verify_error = verify_results.get(asset.id, (None, "未执行验证"))
                asset.status_code = status_code
                asset.verified = status_code is not None
                source_meta = dict(asset.source_meta or {})
                if verify_error:
                    source_meta["verify_error"] = verify_error
                    result.verified_failed += 1
                    job_logger.warning(
                        "Verify failed asset_id=%s url=%s reason=%s",
                        asset.id,
                        asset.normalized_url,
                        verify_error,
                    )
                else:
                    source_meta.pop("verify_error", None)
                    result.verified_success += 1
                    job_logger.info(
                        "Verify success asset_id=%s url=%s status=%s",
                        asset.id,
                        asset.normalized_url,
                        status_code,
                    )
                asset.source_meta = source_meta
            db.commit()
        except Exception as exc:
            for asset in ordered_assets:
                source_meta = dict(asset.source_meta or {})
                source_meta["verify_error"] = str(exc)
                asset.source_meta = source_meta
                asset.verified = False
                result.verified_failed += 1
                job_logger.warning(
                    "Verify failed asset_id=%s url=%s reason=%s",
                    asset.id,
                    asset.normalized_url,
                    exc,
                )
            db.commit()

        job_logger.info("Verify post-process finished success=%s failed=%s", result.verified_success, result.verified_failed)

        from app.core.config import settings
        from app.services.screenshot.service import build_output_filename, run_screenshot_job

        output_dir = Path(settings.screenshot_output_dir)
        result_csv = Path(settings.result_output_dir) / "assetmap_results.csv"
        summary_txt = Path(settings.result_output_dir) / "assetmap_summary.txt"

        asset_rows = [
            {
                "seq": asset.id,
                "host": asset.domain or asset.normalized_url,
                "title": asset.title or "未命名站点",
                "url": asset.normalized_url,
            }
            for asset in ordered_assets
        ]

        if asset_rows:
            job_logger.info("Screenshot post-process start assets=%s", len(asset_rows))
            try:
                run_coro_in_fresh_loop(
                    run_screenshot_job(
                        asset_rows=asset_rows,
                        output_dir=output_dir,
                        result_csv=result_csv,
                        summary_txt=summary_txt,
                        skip_existing=True,
                    )
                )
            except Exception as exc:
                for asset in ordered_assets:
                    source_meta = dict(asset.source_meta or {})
                    source_meta["screenshot_error"] = str(exc)
                    asset.source_meta = source_meta
                    asset.screenshot_status = "failed"
                    result.screenshot_failed += 1
                    job_logger.warning(
                        "Screenshot failed asset_id=%s reason=%s",
                        asset.id,
                        exc,
                    )
                db.commit()
            else:
                if is_job_cancelled(db, job_id):
                    return

                for asset in ordered_assets:
                    source_meta = dict(asset.source_meta or {})
                    file_name = build_output_filename(asset.id, asset.title or "未命名站点", asset.normalized_url)
                    screenshot_path = output_dir / file_name
                    db.query(Screenshot).filter(Screenshot.web_endpoint_id == asset.id).delete(synchronize_session=False)
                    if screenshot_path.exists():
                        asset.screenshot_status = "success"
                        source_meta.pop("screenshot_error", None)
                        db.add(
                            Screenshot(
                                web_endpoint_id=asset.id,
                                file_name=file_name,
                                object_path=str(screenshot_path),
                                status="success",
                            )
                        )
                        result.screenshot_success += 1
                        job_logger.info("Screenshot success asset_id=%s file=%s", asset.id, file_name)
                    else:
                        asset.screenshot_status = "failed"
                        source_meta["screenshot_error"] = "截图文件未生成"
                        result.screenshot_failed += 1
                        job_logger.warning("Screenshot failed asset_id=%s reason=missing-file", asset.id)
                    asset.source_meta = source_meta
                db.commit()
                job_logger.info(
                    "Screenshot post-process finished success=%s failed=%s",
                    result.screenshot_success,
                    result.screenshot_failed,
                )

        job_logger.info(
            "Auto verify finished verify_success=%s verify_failed=%s screenshot_success=%s screenshot_failed=%s",
            result.verified_success,
            result.verified_failed,
            result.screenshot_success,
            result.screenshot_failed,
        )
    except Exception as exc:
        job_logger.exception("Post-process failed: %s", exc)
    finally:
        _close_job_logger(task_logger, file_handler)
        db.close()
