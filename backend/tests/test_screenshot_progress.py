from types import SimpleNamespace
from unittest.mock import patch
import asyncio

from fastapi.testclient import TestClient

from app.api import screenshots as screenshots_api
from app.main import app
from app.models.support import Screenshot
from app.services.screenshot import core as screenshot_core

client = TestClient(app)


class FakeQuery:
    def __init__(self, items):
        self.items = items

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return self.items

    def delete(self, synchronize_session=False):
        return 1


class FakeDB:
    def __init__(self, assets):
        self.assets = assets
        self.committed = False
        self.added = []

    def query(self, _model):
        return FakeQuery(self.assets)

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.committed = False

    def close(self):
        return None


def test_batch_screenshots_returns_task_id_immediately():
    assets = [SimpleNamespace(id='asset-1', normalized_url='https://example.com', domain='example.com', title='Example')]
    fake_db = FakeDB(assets)

    app.dependency_overrides[screenshots_api.get_db] = lambda: fake_db
    try:
        with patch('app.api.screenshots.start_screenshot_task', side_effect=lambda *args, **kwargs: None):
            response = client.post('/api/v1/screenshots/batch', json={'asset_ids': ['asset-1'], 'skip_existing': True})
    finally:
        app.dependency_overrides.clear()
        screenshots_api.SCREENSHOT_TASKS.clear()

    assert response.status_code == 200
    body = response.json()
    assert 'task_id' in body
    assert body['status'] in {'pending', 'running'}


def test_batch_recover_screenshots_returns_task_id_immediately():
    assets = [SimpleNamespace(id='asset-1', normalized_url='https://example.com', domain='example.com', title='Example', screenshot_status='success')]
    fake_db = FakeDB(assets)

    app.dependency_overrides[screenshots_api.get_db] = lambda: fake_db
    try:
        with patch('app.api.screenshots.start_screenshot_task', side_effect=lambda *args, **kwargs: None):
            response = client.post('/api/v1/screenshots/recover', json={'asset_ids': ['asset-1'], 'skip_existing': False})
    finally:
        app.dependency_overrides.clear()
        screenshots_api.SCREENSHOT_TASKS.clear()

    assert response.status_code == 200
    body = response.json()
    assert 'task_id' in body
    assert body['status'] in {'pending', 'running'}


def test_cancel_screenshot_task_marks_task_cancelled():
    task = SimpleNamespace(
        task_id='shot-task-1',
        task_type='asset_screenshot',
        status='running',
        total=3,
        processed=1,
        success=1,
        failed=0,
        message='正在截图 1 / 3',
        cancel_requested=False,
    )
    screenshots_api.SCREENSHOT_TASKS[task.task_id] = task
    try:
        response = client.post(f'/api/v1/screenshots/batch/{task.task_id}/cancel')
    finally:
        screenshots_api.SCREENSHOT_TASKS.clear()

    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'cancelled'
    assert body['processed'] == 1
    assert body['success'] == 1


def test_get_screenshot_task_returns_progress():
    task = SimpleNamespace(
        task_id='shot-task-2',
        task_type='asset_screenshot',
        status='running',
        total=4,
        processed=2,
        success=2,
        failed=0,
        message='正在截图 2 / 4',
        cancel_requested=False,
    )
    screenshots_api.SCREENSHOT_TASKS[task.task_id] = task
    try:
        response = client.get(f'/api/v1/screenshots/batch/{task.task_id}')
    finally:
        screenshots_api.SCREENSHOT_TASKS.clear()

    assert response.status_code == 200
    assert response.json()['processed'] == 2
    assert response.json()['message'] == '正在截图 2 / 4'


def test_start_screenshot_task_persists_actual_output_path(tmp_path):
    assets = [SimpleNamespace(id='asset-1-very-long-uuid', normalized_url='https://example.com', domain='example.com', title='Example', screenshot_status='none')]
    fake_db = FakeDB(assets)
    task = SimpleNamespace(
        task_id='shot-task-write',
        task_type='asset_screenshot',
        status='pending',
        total=1,
        processed=0,
        success=0,
        failed=0,
        message='正在截图 0 / 1',
        cancel_requested=False,
    )
    actual_path = tmp_path / 'asset-1-very-long-uu_404 Not Found_https___example.com.png'

    with patch('app.api.screenshots.SessionLocal', return_value=fake_db), patch('app.api.screenshots.settings.screenshot_output_dir', str(tmp_path)), patch('app.api.screenshots.settings.result_output_dir', str(tmp_path)), patch('app.api.screenshots.run_screenshot_job', return_value={'summary_text': 'ok', 'results': [{'status': 'success', 'screenshot_path': str(actual_path)}]}):
        screenshots_api.start_screenshot_task(task, ['asset-1-very-long-uuid'], False)

        import time
        for _ in range(50):
            if task.status == 'completed':
                break
            time.sleep(0.02)

    assert task.status == 'completed'
    assert len(fake_db.added) == 1
    assert fake_db.added[0].object_path == str(actual_path)
    assert fake_db.added[0].file_name == actual_path.name


def test_run_batch_creates_browser_context_ignoring_https_errors(monkeypatch, tmp_path):
    recorded = {}

    class FakeContext:
        async def add_init_script(self, script):
            return None

        async def close(self):
            return None

    class FakeBrowser:
        async def new_context(self, **kwargs):
            recorded.update(kwargs)
            return FakeContext()

        async def close(self):
            return None

    class FakeChromium:
        async def launch(self, **kwargs):
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

    class FakeAsyncPlaywright:
        async def __aenter__(self):
            return FakePlaywright()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def fake_run_one_asset(*_args, **_kwargs):
        return {'seq': '1', 'status': 'success', 'error': '', 'final_url': 'https://example.com', 'input': 'https://example.com', 'screenshot_path': str(tmp_path / 'x.png')}

    import sys
    from types import SimpleNamespace as SNS

    monkeypatch.setitem(sys.modules, 'playwright.async_api', SNS(async_playwright=lambda: FakeAsyncPlaywright()))
    monkeypatch.setattr(screenshot_core, 'run_one_asset', fake_run_one_asset)

    results = asyncio.run(
        screenshot_core.run_batch(
            assets=[{'seq': '1', 'url': 'https://example.com', 'title': 'Example', 'host': 'example.com'}],
            out_dir=tmp_path,
            timeout_sec=1,
            wait_after_load=0,
            concurrency=1,
            retry_count=1,
            skip_existing=False,
            headful=False,
            logger=None,
        )
    )

    assert len(results) == 1
    assert recorded['ignore_https_errors'] is True
