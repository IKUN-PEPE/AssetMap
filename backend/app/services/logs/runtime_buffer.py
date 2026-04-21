from __future__ import annotations

import logging
from collections import deque
from datetime import datetime
from threading import Lock

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


runtime_log_buffer = RuntimeLogBuffer(max_items=500)
runtime_log_handler = RuntimeLogHandler(runtime_log_buffer)
