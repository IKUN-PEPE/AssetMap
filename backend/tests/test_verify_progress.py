import asyncio
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import assets as assets_api
from app.models.support import Screenshot

app = FastAPI()
app.include_router(assets_api.router, prefix="/api/v1/assets")
client = TestClient(app)


class FakeQuery:
    def __init__(self, assets):
        self.assets = assets

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return self.assets


class FakeDeleteQuery:
    def __init__(self, on_delete):
        self.on_delete = on_delete

    def filter(self, *_args, **_kwargs):
        return self

    def delete(self, synchronize_session=False):
        self.on_delete(synchronize_session)
        return 1


class FakeDB:
    def __init__(self, assets):
        self.assets = assets
        self.committed = False
        self.added = []
        self.deleted_sync_flags = []

    def query(self, model):
        if model is Screenshot:
            return FakeDeleteQuery(lambda synchronize_session: self.deleted_sync_flags.append(synchronize_session))
        return FakeQuery(self.assets)

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.committed = False

    def close(self):
        pass

    def get(self, model, id):
        for item in self.assets:
            if item.id == id:
                return item
        return None


def test_verify_batch_returns_task_id_instead_of_final_counts():
    assets = [SimpleNamespace(id="asset-1", normalized_url="https://example.com", verified=False, status_code=None)]
    fake_db = FakeDB(assets)

    app.dependency_overrides[assets_api.get_db] = lambda: fake_db
    try:
        with patch("app.api.assets.start_verify_task_async") as start_task_mock:
            response = client.post("/api/v1/assets/verify-batch", json={"asset_ids": ["asset-1"], "verified": True})
    finally:
        app.dependency_overrides.clear()
        assets_api.VERIFY_TASKS.clear()

    assert response.status_code == 200
    body = response.json()
    assert "task_id" in body
    assert body["status"] in {"pending", "running"}
    start_task_mock.assert_called_once()


def test_cancel_verify_task_marks_task_cancelled_without_resetting_progress():
    task = SimpleNamespace(task_id="task-cancel", task_type="asset_verify", status="running", total=3, processed=1, success=1, failed=0, message="正在验证 1 / 3", cancel_requested=False)
    assets_api.VERIFY_TASKS[task.task_id] = task
    try:
        response = client.post(f"/api/v1/assets/verify-batch/{task.task_id}/cancel")
    finally:
        assets_api.VERIFY_TASKS.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert response.json()["processed"] == 1
    assert response.json()["success"] == 1


@pytest.mark.asyncio
async def test_start_verify_task_async_executes_correctly():
    task = SimpleNamespace(task_id="task-1", task_type="asset_verify", status="pending", total=1, processed=0, success=0, failed=0, message="", cancel_requested=False)

    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_browser.new_context.return_value = mock_context

    mock_playwright = MagicMock()
    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

    with patch("app.api.assets.async_playwright") as mock_ap, patch("app.api.assets.process_one_asset", new_callable=AsyncMock) as mock_process:
        mock_ap.return_value.__aenter__.return_value = mock_playwright
        await assets_api.start_verify_task_async(task, ["a1"], True, [("a1", "url1")])

    assert task.status == "completed"
    mock_process.assert_called_once()


def test_get_verify_task_returns_current_progress():
    task = SimpleNamespace(task_id="task-1", task_type="asset_verify", status="running", total=3, processed=2, success=1, failed=1, message="正在验证 2 / 3", cancel_requested=False)
    assets_api.VERIFY_TASKS["task-1"] = task
    try:
        response = client.get("/api/v1/assets/verify-batch/task-1")
    finally:
        assets_api.VERIFY_TASKS.clear()

    assert response.status_code == 200
    assert response.json()["processed"] == 2
    assert response.json()["message"] == "正在验证 2 / 3"
