from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models import Host, Service, SourceObservation, WebEndpoint
from app.services.normalizer.service import normalize_url

from .collect_identity import _safe_port, _safe_text


def _append_post_process_job_link(source_meta: dict[str, Any], job_id: str) -> dict[str, Any]:
    linked_job_ids = source_meta.get("post_process_job_ids")
    if not isinstance(linked_job_ids, list):
        linked_job_ids = []

    normalized_job_ids: list[str] = []
    for item in linked_job_ids:
        value = _safe_text(item)
        if value and value not in normalized_job_ids:
            normalized_job_ids.append(value)

    current_job_id = str(job_id)
    if current_job_id not in normalized_job_ids:
        normalized_job_ids.append(current_job_id)

    source_meta["post_process_job_ids"] = normalized_job_ids
    if not _safe_text(source_meta.get("post_process_job_id")):
        source_meta["post_process_job_id"] = current_job_id
    return source_meta


def _append_stage_job_link(source_meta: dict[str, Any], stage_key: str, job_id: str) -> dict[str, Any]:
    stage_job_ids = source_meta.get(stage_key)
    if not isinstance(stage_job_ids, list):
        stage_job_ids = []

    normalized_job_ids: list[str] = []
    for item in stage_job_ids:
        value = _safe_text(item)
        if value and value not in normalized_job_ids:
            normalized_job_ids.append(value)

    current_job_id = str(job_id)
    if current_job_id not in normalized_job_ids:
        normalized_job_ids.append(current_job_id)

    source_meta[stage_key] = normalized_job_ids
    return source_meta


def _find_existing_web_endpoint(asset_db: Session, resolved: dict[str, Any]) -> WebEndpoint | None:
    entry_url_hash = _safe_text(resolved.get("entry_url_hash"))
    if not entry_url_hash:
        return None

    existing = (
        asset_db.query(WebEndpoint)
        .filter(WebEndpoint.source_meta["entry_url_hash"].astext == entry_url_hash)
        .first()
    )
    if existing:
        return existing

    return asset_db.query(WebEndpoint).filter(WebEndpoint.normalized_url_hash == entry_url_hash).first()


def _build_asset_lookup_indexes(assets: list[WebEndpoint]) -> dict[str, dict[Any, WebEndpoint]]:
    by_id: dict[Any, WebEndpoint] = {}
    by_url: dict[Any, WebEndpoint] = {}
    by_identity: dict[Any, WebEndpoint] = {}
    by_source_record: dict[Any, WebEndpoint] = {}
    by_domain_port: dict[Any, WebEndpoint] = {}
    by_host_port: dict[Any, WebEndpoint] = {}
    by_ip_port: dict[Any, WebEndpoint] = {}
    by_domain: dict[Any, WebEndpoint] = {}
    by_host: dict[Any, WebEndpoint] = {}
    by_ip: dict[Any, WebEndpoint] = {}

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
        host = _safe_text(source_meta.get("host") or source_meta.get("subdomain") or domain or getattr(host_obj, "name", None))
        ip = _safe_text((getattr(host_obj, "ip", None) if host_obj else None) or source_meta.get("ip"))
        port = _safe_port((getattr(service, "port", None) if service else None) or source_meta.get("port"))
        if domain:
            by_domain[domain] = asset
        if host:
            by_host[host] = asset
        if ip:
            by_ip[ip] = asset
        if domain and port is not None:
            by_domain_port[(domain, port)] = asset
        if host and port is not None:
            by_host_port[(host, port)] = asset
        if ip and port is not None:
            by_ip_port[(ip, port)] = asset

    return {
        "by_id": by_id,
        "by_url": by_url,
        "by_identity": by_identity,
        "by_source_record": by_source_record,
        "by_domain_port": by_domain_port,
        "by_host_port": by_host_port,
        "by_ip_port": by_ip_port,
        "by_domain": by_domain,
        "by_host": by_host,
        "by_ip": by_ip,
    }


def _resolve_asset_id_from_payload(
    raw_payload: dict[str, Any],
    indexes: dict[str, dict[Any, WebEndpoint]],
    source_record_id: str | None = None,
) -> str | None:
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
        raw_payload.get("normalized_url")
        or raw_payload.get("entry_url")
        or raw_payload.get("fallback_url")
        or raw_payload.get("url")
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
    host = _safe_text(raw_payload.get("resolved_host") or raw_payload.get("host") or raw_payload.get("subdomain") or domain)
    ip = _safe_text(raw_payload.get("resolved_ip") or raw_payload.get("ip"))
    port = _safe_port(raw_payload.get("resolved_port") or raw_payload.get("port"))

    if domain and port is not None:
        asset = indexes["by_domain_port"].get((domain, port))
        if asset is not None and getattr(asset, "id", None):
            return asset.id
    if host and port is not None:
        asset = indexes["by_host_port"].get((host, port))
        if asset is not None and getattr(asset, "id", None):
            return asset.id
    if ip and port is not None:
        asset = indexes["by_ip_port"].get((ip, port))
        if asset is not None and getattr(asset, "id", None):
            return asset.id
    if domain:
        asset = indexes["by_domain"].get(domain)
        if asset is not None and getattr(asset, "id", None):
            return asset.id
    if host:
        asset = indexes["by_host"].get(host)
        if asset is not None and getattr(asset, "id", None):
            return asset.id
    if ip:
        asset = indexes["by_ip"].get(ip)
        if asset is not None and getattr(asset, "id", None):
            return asset.id
    return None


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
        return or_(WebEndpoint.domain == domain, WebEndpoint.source_meta["domain"].astext == domain)

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
        raw_payload = obs.raw_payload or {}
        if raw_payload.get("web_endpoint_id"):
            ids.add(str(raw_payload.get("web_endpoint_id")))
        if getattr(obs, "source_record_id", None) or raw_payload.get("source_record_id"):
            source_record_ids.add(str(getattr(obs, "source_record_id", None) or raw_payload.get("source_record_id")))
        normalized_url = _safe_text(
            raw_payload.get("normalized_url")
            or raw_payload.get("entry_url")
            or raw_payload.get("fallback_url")
            or raw_payload.get("url")
        )
        if normalized_url:
            try:
                urls.add(normalize_url(normalized_url))
            except Exception:
                urls.add(normalized_url)
        if raw_payload.get("asset_identity_key"):
            identity_keys.add(str(raw_payload.get("asset_identity_key")))
        domain = _safe_text(raw_payload.get("resolved_domain") or raw_payload.get("domain"))
        host = _safe_text(raw_payload.get("resolved_host") or raw_payload.get("host") or raw_payload.get("subdomain") or domain)
        ip = _safe_text(raw_payload.get("resolved_ip") or raw_payload.get("ip"))
        port = _safe_port(raw_payload.get("resolved_port") or raw_payload.get("port"))
        if domain:
            domains.add(domain)
            if port is not None:
                domain_port_pairs.add((domain, port))
        if host:
            hosts.add(host)
            if port is not None:
                host_port_pairs.add((host, port))
        if ip:
            ips.add(ip)
            if port is not None:
                ip_port_pairs.add((ip, port))

    filters = []
    if ids:
        filters.append(WebEndpoint.id.in_(sorted(ids)))
    if urls:
        filters.append(WebEndpoint.normalized_url.in_(sorted(urls)))
    if domain_port_pairs:
        filters.append(
            or_(
                *[
                    and_(
                        _domain_match(domain),
                        _port_match(port),
                    )
                    for domain, port in sorted(domain_port_pairs)
                ]
            )
        )
    if host_port_pairs:
        filters.append(
            or_(
                *[
                    and_(
                        or_(
                            WebEndpoint.source_meta["host"].astext == host,
                            WebEndpoint.source_meta["subdomain"].astext == host,
                            WebEndpoint.domain == host,
                            WebEndpoint.source_meta["domain"].astext == host,
                        ),
                        _port_match(port),
                    )
                    for host, port in sorted(host_port_pairs)
                ]
            )
        )
    if ip_port_pairs:
        filters.append(
            or_(
                *[
                    and_(
                        _ip_match(ip),
                        _port_match(port),
                    )
                    for ip, port in sorted(ip_port_pairs)
                ]
            )
        )
    if domains:
        filters.append(or_(WebEndpoint.domain.in_(sorted(domains)), WebEndpoint.source_meta["domain"].astext.in_(sorted(domains))))
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
    if source_record_ids:
        filters.append(WebEndpoint.source_meta["source_record_id"].astext.in_(sorted(source_record_ids)))
    if identity_keys:
        filters.append(WebEndpoint.source_meta["asset_identity_key"].astext.in_(sorted(identity_keys)))

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


def _build_job_scoped_asset_query(db: Session, job_id: str):
    query = db.query(WebEndpoint)
    if callable(getattr(query, "outerjoin", None)):
        return query.filter(
            or_(
                WebEndpoint.source_meta["import_job_id"].astext == str(job_id),
                WebEndpoint.source_meta["post_process_job_id"].astext == str(job_id),
                WebEndpoint.source_meta["post_process_job_ids"].contains([str(job_id)]),
            )
        )
    return query.filter(WebEndpoint.id.in_([]))


def _iter_job_scoped_assets(db: Session, job_id: str) -> list[WebEndpoint]:
    scoped_assets = _build_job_scoped_asset_query(db, job_id).all()
    target_ids = _collect_job_asset_ids(db, job_id)
    ordered_assets: list[WebEndpoint] = []
    seen_ids: set[str] = set()

    for asset in scoped_assets:
        asset_id = getattr(asset, "id", None)
        if not asset_id or asset_id in seen_ids:
            continue
        seen_ids.add(asset_id)
        ordered_assets.append(asset)

    if target_ids:
        target_assets = db.query(WebEndpoint).filter(WebEndpoint.id.in_(target_ids)).all()
        assets_by_id = {asset.id: asset for asset in target_assets}
        for asset_id in target_ids:
            asset = assets_by_id.get(asset_id)
            if asset is None or asset_id in seen_ids:
                continue
            seen_ids.add(asset_id)
            ordered_assets.append(asset)

    return ordered_assets
