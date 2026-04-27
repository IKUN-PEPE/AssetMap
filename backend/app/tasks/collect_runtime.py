import asyncio
import logging
from typing import Any, Dict

import httpx
from sqlalchemy.orm import Session

from app.core.config import BASE_DIR
from app.models import CollectJob

from .collect_identity import _safe_text, _utcnow_naive

logger = logging.getLogger(__name__)


class _JobFileHandlerFilter(logging.Filter):
    def __init__(self, job_id: str):
        super().__init__()
        self.job_id = str(job_id)

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover
        return getattr(record, "job_id", None) == self.job_id


class JobLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra = kwargs.get("extra") or {}
        extra["job_id"] = self.extra["job_id"]
        kwargs["extra"] = extra
        return msg, kwargs


def _apply_job_counters(job: CollectJob, *, success: int = 0, duplicate: int = 0, failed: int = 0) -> None:
    job.success_count = int(getattr(job, "success_count", 0) or 0) + int(success)
    job.duplicate_count = int(getattr(job, "duplicate_count", 0) or 0) + int(duplicate)
    job.failed_count = int(getattr(job, "failed_count", 0) or 0) + int(failed)
    job.total_count = int(job.success_count) + int(job.failed_count) + int(job.duplicate_count)


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


def load_job(db: Session, job_id: str):
    return db.query(CollectJob).filter(CollectJob.id == job_id).first()


def is_job_cancelled(db: Session, job_id: str) -> bool:
    current = load_job(db, job_id)
    return bool(current and current.status == "cancelled")


def finish_cancelled_job(job: CollectJob, db: Session, *, job_logger: JobLoggerAdapter | None = None) -> None:
    job.status = "cancelled"
    job.finished_at = _utcnow_naive()
    db.commit()
    if job_logger is not None:
        job_logger.info("Task cancelled")


def _mark_job_source_failure(db: Session, job: CollectJob, source_name: str, error_message: str) -> None:
    _apply_job_counters(job, failed=1)
    job.error_message = " | ".join(filter(None, [job.error_message, f"{source_name} failed: {error_message}"]))
    db.commit()
