from datetime import datetime, timedelta, UTC

from app.services.logs.runtime_buffer import RuntimeLogBuffer


def test_runtime_log_buffer_filters_by_source_and_since():
    buffer = RuntimeLogBuffer(max_items=5)
    now = datetime.now(UTC)

    buffer.append(
        {
            "timestamp": (now - timedelta(seconds=2)).isoformat(),
            "level": "info",
            "source": "service",
            "message": "service started",
        }
    )
    buffer.append(
        {
            "timestamp": now.isoformat(),
            "level": "info",
            "source": "task",
            "message": "job created",
        }
    )

    items = buffer.list_recent(source="task", since=(now - timedelta(seconds=1)).isoformat(), limit=10)

    assert [item["message"] for item in items] == ["job created"]
