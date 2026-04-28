from __future__ import annotations

import logging
import time
from collections import deque
from datetime import datetime
from logging.handlers import RotatingFileHandler
from threading import Lock

from app.core.config import BASE_DIR

TASK_LOGGER_PREFIXES = (
    "app.tasks.",
    "app.api.jobs",
    "app.api.screenshots",
    "app.api.assets",
    "assetmap.screenshot",
    "app.services.collectors.",
)


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _classify_log_source(logger_name: str) -> str:
    if any(logger_name.startswith(prefix) for prefix in TASK_LOGGER_PREFIXES):
        return "task"
    return "service"


class RuntimeLogBuffer:
    def __init__(self, max_items: int = 500):
        self._items = deque(maxlen=max_items)
        self._lock = Lock()

    def append(self, item: dict) -> None:
        with self._lock:
            self._items.append(item)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def list_recent(self, source: str = "all", since: str | None = None, limit: int = 200) -> list[dict]:
        with self._lock:
            items = list(self._items)

        if source != "all":
            items = [item for item in items if item["source"] == source]
        if since:
            since_dt = _parse_timestamp(since)
            items = [item for item in items if _parse_timestamp(item["timestamp"]) > since_dt]
        items.sort(key=lambda item: _parse_timestamp(item["timestamp"]))
        return items[-limit:]


class RuntimeLogHandler(logging.Handler):
    def __init__(self, buffer: RuntimeLogBuffer):
        super().__init__()
        self.buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        self.buffer.append(
            {
                "timestamp": datetime.now().astimezone().isoformat(),
                "level": record.levelname.lower(),
                "source": _classify_log_source(record.name),
                "message": self.format(record),
            }
        )


class ServiceLogFileFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return _classify_log_source(record.name) == "service"


class UTCFormatter(logging.Formatter):
    converter = time.gmtime


SERVICE_LOG_DIR = BASE_DIR / "logs"
SERVICE_LOG_DIR.mkdir(parents=True, exist_ok=True)
SERVICE_LOG_FILE = SERVICE_LOG_DIR / "service.log"
service_log_handler = RotatingFileHandler(
    SERVICE_LOG_FILE,
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
service_log_handler.setFormatter(
    UTCFormatter(
        "%(asctime)sZ - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
)
service_log_handler.addFilter(ServiceLogFileFilter())


def read_recent_service_logs(*, limit: int = 200, since: str | None = None) -> list[dict]:
    if not SERVICE_LOG_FILE.exists():
        return []

    lines = deque(maxlen=limit * 5)
    with SERVICE_LOG_FILE.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if line:
                lines.append(line)

    items: list[dict] = []
    for line in lines:
        try:
            timestamp, level, logger_name, message = line.split(" - ", 3)
        except ValueError:
            continue
        items.append(
            {
                "timestamp": timestamp.replace("Z", "+00:00"),
                "level": level.lower(),
                "source": "service",
                "message": message,
            }
        )

    if since:
        since_dt = _parse_timestamp(since)
        items = [item for item in items if _parse_timestamp(item["timestamp"]) > since_dt]

    items.sort(key=lambda item: _parse_timestamp(item["timestamp"]))
    return items[-limit:]


runtime_log_buffer = RuntimeLogBuffer(max_items=500)
runtime_log_handler = RuntimeLogHandler(runtime_log_buffer)
