import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api import assets as assets_api
from app.api.assets import fetch_status_code_with_playwright
from app.main import app

client = TestClient(app)


class FakeQuery:
    def __init__(self, items):
        self.items = items

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return self.items

    def delete(self, synchronize_session=False):
        return 0


class FakeDB:
    def __init__(self, items):
        self.items = items
        self.committed = False

    def query(self, _model):
        return FakeQuery(self.items)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.committed = False

    def close(self):
        pass

    def add(self, item):
        pass

    def get(self, model, id):
        for item in self.items:
            if item.id == id:
                return item
        return None


@pytest.mark.asyncio
async def test_fetch_status_code_with_playwright_requests_response_without_waiting_for_domcontentloaded():
    page = AsyncMock()
    response = MagicMock(status=200)
    page.goto.return_value = response
    context = AsyncMock()
    context.new_page.return_value = page

    status_code = await fetch_status_code_with_playwright(context, "https://example.com")

    assert status_code == 200
    page.goto.assert_called_once_with("https://example.com", wait_until="commit", timeout=8000)
    page.close.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_status_code_with_playwright_returns_none_when_no_response():
    page = AsyncMock()
    page.goto.return_value = None
    context = AsyncMock()
    context.new_page.return_value = page

    status_code = await fetch_status_code_with_playwright(context, "https://example.com")

    assert status_code is None
    page.close.assert_called_once()


def test_verify_batch_returns_task_id_immediately():
    assets = [
        SimpleNamespace(id="asset-1", normalized_url="https://example.com", verified=False, status_code=None),
    ]
    fake_db = FakeDB(assets)

    app.dependency_overrides[assets_api.get_db] = lambda: fake_db
    try:
        with patch("app.api.assets.start_verify_task_async") as start_task_mock:
            response = client.post(
                "/api/v1/assets/verify-batch",
                json={"asset_ids": ["asset-1"], "verified": True},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert "task_id" in body
    assert body["status"] == "pending"
    start_task_mock.assert_called_once()


@pytest.mark.asyncio
async def test_process_one_asset_updates_db_and_task_progress():
    from app.api.assets import process_one_asset
    
    asset = SimpleNamespace(id="asset-1", normalized_url="https://ok.com", verified=False, status_code=None)
    fake_db = FakeDB([asset])
    task = SimpleNamespace(
        task_id="task-1",
        task_type="asset_verify",
        status="running",
        total=1,
        processed=0,
        success=0,
        failed=0,
        message="",
        cancel_requested=False
    )
    context = AsyncMock()
    semaphore = asyncio.Semaphore(1)

    with patch("app.api.assets.fetch_status_code_with_playwright", return_value=200), \
         patch("app.api.assets.capture_asset_screenshot_async", return_value="/tmp/shot.png"), \
         patch("app.api.assets.SessionLocal", return_value=fake_db):
        
        await process_one_asset("asset-1", "https://ok.com", True, context, task, semaphore)

    assert task.processed == 1
    assert task.success == 1
    assert asset.status_code == 200
    assert asset.verified is True
    assert fake_db.committed is True
