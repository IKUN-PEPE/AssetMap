from datetime import datetime, timezone
from typing import Any, Dict
from urllib.parse import urlsplit

from app.models import WebEndpoint
from app.services.collectors.base import BaseCollector
from app.services.normalizer.service import build_url_hash, normalize_url


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


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _observation_only_success_bucket(resolved: dict[str, Any]) -> bool:
    return any(
        [
            _safe_text(resolved.get("domain")),
            _safe_text(resolved.get("host")),
            _safe_text(resolved.get("ip")),
            resolved.get("port") is not None,
            _safe_text(resolved.get("normalized_url")),
        ]
    )


def _build_url_from_asset(asset_data: dict[str, Any]) -> str | None:
    protocol = _normalize_protocol(asset_data.get("protocol"), default="https")
    if _is_non_web_protocol(protocol):
        return None

    raw_url = _safe_text(asset_data.get("url"))
    if raw_url:
        if raw_url.lower().startswith(("http://", "https://")):
            return raw_url
        direct_url = BaseCollector.build_url(url=raw_url)
        if direct_url:
            return direct_url

    return _build_fallback_endpoint_url(
        protocol=protocol,
        host=(
            _safe_text(asset_data.get("host"))
            or _safe_text(asset_data.get("subdomain"))
            or _safe_text(asset_data.get("domain"))
        ),
        ip=_safe_text(asset_data.get("ip")),
        port=_safe_port(asset_data.get("port")),
    )


def _extract_host_from_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parts = urlsplit(url if url.lower().startswith(("http://", "https://")) else f"https://{url}")
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
    if port is not None:
        return f"{scheme}://{target}:{port}"

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
    protocol = _safe_text(resolved.get("protocol"))
    ip = _safe_text(resolved.get("ip"))
    port = resolved.get("port")
    if ip and port is not None:
        if protocol and _is_non_web_protocol(protocol):
            return f"{protocol}:ip-port:{ip}:{port}"
        return f"ip-port:{ip}:{port}"
    host = _safe_text(resolved.get("host")) or _safe_text(resolved.get("domain"))
    port = resolved.get("port")
    if host and port is not None:
        if protocol and _is_non_web_protocol(protocol):
            return f"{protocol}:host-port:{host}:{port}"
        return f"host-port:{host}:{port}"
    return None


def _build_source_record_id(source_name: str, resolved: dict[str, Any]) -> str | None:
    identity_key = _build_asset_identity_key(resolved, source_name)
    if identity_key:
        return f"{source_name}:{identity_key}"
    return None


def _build_web_source_meta(
    source_name: str,
    job_id: str,
    asset_data: Dict[str, Any],
    resolved: dict[str, Any],
    identity_key: str | None,
    source_record_id: str | None,
) -> dict[str, Any]:
    return {
        "source": source_name,
        "import_job_id": job_id,
        "raw": asset_data.get("raw_data"),
        "asset_identity_key": identity_key,
        "source_record_id": source_record_id,
        "entry_url": resolved.get("entry_url"),
        "entry_url_hash": resolved.get("entry_url_hash"),
        "domain": resolved.get("domain"),
        "host": resolved.get("host"),
        "ip": resolved.get("ip"),
        "port": resolved.get("port"),
    }


def _serialize_observation_payload(
    asset_data: Dict[str, Any],
    resolved: dict[str, Any],
    source_name: str,
    web: WebEndpoint | None,
) -> dict[str, Any]:
    raw_payload = dict(asset_data.get("raw_data") or {})
    if web is not None and getattr(web, "id", None):
        raw_payload["web_endpoint_id"] = getattr(web, "id")

    normalized_url = _safe_text(resolved.get("normalized_url"))
    entry_url = _safe_text(resolved.get("entry_url"))
    raw_payload.update(
        {
            "source": source_name,
            "url": _safe_text(asset_data.get("url")) or normalized_url or entry_url,
            "normalized_url": normalized_url,
            "entry_url": entry_url,
            "resolved_host": resolved.get("host"),
            "resolved_ip": resolved.get("ip"),
            "resolved_domain": resolved.get("domain"),
            "resolved_port": resolved.get("port"),
            "resolved_protocol": resolved.get("protocol"),
            "asset_identity_key": _build_asset_identity_key(resolved, source_name),
            "source_record_id": _build_source_record_id(source_name, resolved),
            "observation_only": web is None,
        }
    )
    return raw_payload


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

    entry_url = _build_fallback_endpoint_url(
        protocol=protocol,
        host=host or domain,
        ip=ip,
        port=port,
    )
    normalized_entry_url = normalize_url(entry_url) if entry_url else None
    normalized_url = normalize_url(direct_url or entry_url) if (direct_url or entry_url) else None

    return {
        "ip": ip,
        "domain": domain,
        "host": host,
        "title": title,
        "protocol": web_protocol or protocol,
        "port": port,
        "url": direct_url,
        "normalized_url": normalized_url,
        "entry_url": normalized_entry_url,
        "entry_url_hash": build_url_hash(normalized_entry_url) if normalized_entry_url else None,
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
    resolved["primary_url"] = resolved.get("normalized_url") or resolved.get("entry_url")
    return resolved
