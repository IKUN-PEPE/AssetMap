from fastapi.testclient import TestClient

from app.main import app
from app.services.logs.runtime_buffer import runtime_log_buffer

client = TestClient(app)


def setup_function():
    runtime_log_buffer.clear()


def test_logs_recent_endpoint_filters_by_source():
    runtime_log_buffer.append(
        {
            "timestamp": "2026-04-13T12:00:00+00:00",
            "level": "info",
            "source": "task",
            "message": "task entry",
        }
    )
    runtime_log_buffer.append(
        {
            "timestamp": "2026-04-13T12:00:01+00:00",
            "level": "info",
            "source": "service",
            "message": "service entry",
        }
    )

    response = client.get("/api/v1/logs/recent", params={"source": "task", "limit": 10})

    assert response.status_code == 200
    assert [item["message"] for item in response.json()["items"]] == ["task entry"]


def test_logs_recent_endpoint_returns_incremental_items():
    runtime_log_buffer.append(
        {
            "timestamp": "2026-04-13T12:00:00+00:00",
            "level": "info",
            "source": "task",
            "message": "old entry",
        }
    )
    runtime_log_buffer.append(
        {
            "timestamp": "2026-04-13T12:00:05+00:00",
            "level": "info",
            "source": "task",
            "message": "new entry",
        }
    )

    response = client.get(
        "/api/v1/logs/recent",
        params={"source": "task", "since": "2026-04-13T12:00:01+00:00", "limit": 10},
    )

    assert response.status_code == 200
    assert [item["message"] for item in response.json()["items"]] == ["new entry"]
    assert response.json()["next_since"] == "2026-04-13T12:00:05+00:00"
