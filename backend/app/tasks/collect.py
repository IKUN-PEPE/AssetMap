import asyncio
import csv
import logging
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.huey import huey, run_in_process
from app.models import CollectJob, JobPendingAsset, SourceObservation, WebEndpoint
from app.models.support import Screenshot
from app.services.collectors import get_collector
from app.services.collectors.fofa_csv import parse_fofa_csv
from app.services.collectors.hunter_csv import parse_hunter_csv
from app.services.collectors.mapped_csv import parse_mapped_csv
from app.services.collectors.quake_csv import parse_quake_csv
from app.services.collectors.zoomeye_csv import parse_zoomeye_csv
from app.services.normalizer.service import build_url_hash, normalize_url
from app.services.system_service import SystemConfigService

from .collect_dedup import (
    _append_post_process_job_link,
    _append_stage_job_link,
    _build_asset_lookup_indexes,
    _build_job_scoped_asset_query as _build_job_scoped_asset_query_impl,
    _build_observation_asset_query,
    _collect_job_asset_ids as _collect_job_asset_ids_impl,
    _find_existing_web_endpoint,
    _resolve_asset_id_from_payload,
)
from .collect_identity import (
    _build_asset_identity_key,
    _build_fallback_endpoint_url,
    _build_source_record_id,
    _build_url_from_asset,
    _build_web_source_meta,
    _ensure_saveable_identity,
    _extract_host_from_url,
    _guess_web_protocol,
    _is_non_web_protocol,
    _looks_like_ip,
    _normalize_company,
    _normalize_protocol,
    _observation_only_success_bucket,
    _resolve_asset_identity,
    _safe_port,
    _safe_text,
    _serialize_observation_payload,
    _utcnow_naive,
)
from .collect_persistence import (
    SaveAssetsResult,
    _create_isolated_asset_session,
    _is_isolated_session_usable,
    _load_job_for_write,
    _record_save_failure,
    _refresh_job_quietly,
    _rollback_session_quietly,
    _save_asset_row_with_session,
    _save_asset_row_with_session as _save_asset_row_with_session_impl,
    _sync_job_counters,
    _upsert_source_observation,
    save_assets,
)
from .collect_post_process import PostProcessResult, run_auto_post_process_impl
from .collect_runtime import (
    JobLoggerAdapter,
    _add_http_trace_hooks,
    _apply_job_counters,
    _bind_http_trace_on_collector,
    _close_job_logger,
    _desensitize_headers,
    _desensitize_url,
    _mark_job_source_failure,
    _open_job_logger,
    finish_cancelled_job,
    is_job_cancelled,
    load_job,
)

logger = logging.getLogger(__name__)
CSV_SOURCE_PARSERS = {
    "fofa": parse_fofa_csv,
    "hunter": parse_hunter_csv,
    "zoomeye": parse_zoomeye_csv,
    "quake": parse_quake_csv,
}


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


def _save_assets_bridge(
    db: Session,
    job: CollectJob,
    assets: list[dict[str, Any]],
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


def _build_job_scoped_asset_query(db: Session, job_id: str):
    return _build_job_scoped_asset_query_impl(db, job_id)


def _collect_job_asset_ids(db: Session, job_id: str) -> list[str]:
    return _collect_job_asset_ids_impl(db, job_id)


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


def _store_pending_assets(
    db: Session,
    job: CollectJob,
    records: list[dict[str, Any]],
    source_name: str,
    *,
    replace_existing: bool = False,
) -> int:
    bind = getattr(db, "bind", None)
    if bind is not None:
        JobPendingAsset.__table__.create(bind=bind, checkfirst=True)
    if replace_existing:
        db.query(JobPendingAsset).filter(JobPendingAsset.job_id == job.id).delete(synchronize_session=False)

    stored = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        raw_data = dict(record.get("raw_data") or record)
        mapped_data = dict(record)
        db.add(
            JobPendingAsset(
                job_id=job.id,
                source=source_name,
                raw_data=raw_data,
                mapped_data=mapped_data,
                status="pending",
            )
        )
        stored += 1
    return stored


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

    stored_count = _store_pending_assets(db, job, records, save_source, replace_existing=True)

    job.success_count = stored_count
    job.duplicate_count = 0
    job.failed_count = failed_rows
    total_rows = _count_csv_rows(file_path)
    if total_rows <= 0:
        total_rows = stored_count + failed_rows
    job.total_count = max(total_rows, stored_count + failed_rows)
    job.progress = 100
    job.status = "pending_import" if stored_count > 0 else "failed"
    db.commit()

    logger_ref.info(
        "CSV import finished parser=%s source=%s total=%s pending=%s failed=%s parser_failed=%s waiting_confirm=%s",
        parser_name,
        save_source,
        job.total_count,
        stored_count,
        int(job.failed_count),
        failed_rows,
        job.status == "pending_import",
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
        job.started_at = _utcnow_naive()
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
                if not sources:
                    job.status = "success"
                    job.progress = 100
                    job.finished_at = _utcnow_naive()
                    job.total_count = int(job.success_count) + int(job.failed_count) + int(job.duplicate_count)
                    db.commit()
                    job_logger.info("Task finished without sources or queries")
                    if bool(getattr(job, "auto_verify", False)) and not is_job_cancelled(db, job.id):
                        job_logger.info("Triggering auto verification and post-process")
                        run_in_process(run_auto_post_process, job.id, delay=2)
                    return
                job.failed_count = int(getattr(job, "failed_count", 0) or 0) + max(len(sources), 1)
                job.total_count = int(job.success_count) + int(job.failed_count) + int(job.duplicate_count)
                job.status = "failed"
                job.progress = 100
                job.finished_at = _utcnow_naive()
                job.error_message = "未提供有效查询条件"
                db.commit()
                job_logger.warning("Task failed reason=no-valid-queries selected_sources=%s", len(sources))
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

                    stored_count = _store_pending_assets(
                        db,
                        job,
                        _prepare_import_records(assets),
                        src_name,
                        replace_existing=False,
                    )
                    job.success_count = int(getattr(job, "success_count", 0) or 0) + stored_count
                    job.total_count = int(job.success_count) + int(job.failed_count)
                    job.progress = int(index / total_queries * 100)
                    db.commit()
                    job_logger.info(
                        "Source staged source=%s progress=%s pending=%s failed=%s",
                        src_name,
                        job.progress,
                        job.success_count,
                        job.failed_count,
                    )

                    if is_job_cancelled(db, job_id):
                        finish_cancelled_job(job, db, job_logger=job_logger)
                        job_logger.info("Task cancelled after source save source=%s", src_name)
                        return
                except Exception as exc:
                    job_logger.exception("Collector %s failed", src_name)
                    source_errors.append(f"{src_name} failed: {exc}")
                    _mark_job_source_failure(db, job, src_name, str(exc))

        if is_job_cancelled(db, job_id):
            finish_cancelled_job(job, db, job_logger=job_logger)
            job_logger.info("Task cancelled before finalize")
            return

        if executed_queries == 0 and "csv_import" not in sources:
            source_errors.append("没有可执行的有效采集查询")
            if not job.error_message:
                job.error_message = " | ".join(source_errors)

        if int(getattr(job, "success_count", 0) or 0) > 0:
            job.status = "pending_import"
        else:
            job.status = _determine_job_status(job, source_errors, executed_queries=executed_queries)
        job.progress = 100
        job.finished_at = _utcnow_naive()
        job.total_count = int(job.success_count) + int(job.failed_count) + int(job.duplicate_count)
        job.error_message = " | ".join(source_errors) or job.error_message or None
        db.commit()

        job_logger.info(
            "Task finished status=%s pending=%s duplicate=%s failed=%s total=%s",
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
        job.failed_count = int(getattr(job, "failed_count", 0) or 0) + 1
        job.total_count = int(job.success_count) + int(job.failed_count) + int(job.duplicate_count)
        job.status = "failed"
        job.finished_at = _utcnow_naive()
        job.error_message = str(exc)
        db.commit()
    finally:
        _close_job_logger(task_logger, file_handler)
        db.close()


@huey.task()
def run_auto_post_process(job_id: str):
    return run_auto_post_process_impl(
        job_id,
        session_factory=SessionLocal,
        open_job_logger=_open_job_logger,
        close_job_logger=_close_job_logger,
        load_job=load_job,
        is_job_cancelled=is_job_cancelled,
        iter_job_scoped_assets=_iter_job_scoped_assets,
        run_coro_in_fresh_loop=run_coro_in_fresh_loop,
        verify_assets_for_post_process=_verify_assets_for_post_process,
        append_post_process_job_link=_append_post_process_job_link,
        append_stage_job_link=_append_stage_job_link,
    )
