from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, JSON, StaticPool, text
from sqlalchemy.orm import sessionmaker
import sqlalchemy.dialects.postgresql as postgresql
import uuid

# Monkeypatch JSONB to JSON for SQLite compatibility in tests
postgresql.JSONB = JSON

from app.main import app
from app.core.db import Base, get_db
from app.models.exposure_search import ExposureSearchTask, ExposureSearchResult
from unittest.mock import patch, MagicMock

# Setup test database
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

client = TestClient(app)

def test_create_exposure_search_task():
    payload = {
        "name": "API Test Task",
        "org_keywords": ["test"],
        "sources": ["bing"],
        "max_results": 25,
        "max_pages": 3,
        "only_documents": True,
        "auto_run": False
    }
    response = client.post("/api/v1/exposure-search/tasks", json=payload)
    assert response.status_code == 200
    assert response.json()["name"] == "API Test Task"
    assert response.json()["max_results"] == 25
    assert response.json()["max_pages"] == 3
    assert response.json()["only_documents"] is True
    assert response.json()["completed_queries"] == 0
    assert response.json()["total_queries"] == 0
    assert response.json()["progress_percent"] == 0


def test_create_exposure_search_task_accepts_legacy_use_playwright():
    payload = {
        "name": "Legacy Playwright Task",
        "org_keywords": ["test"],
        "sources": ["bing"],
        "use_playwright": True,
        "auto_run": False,
    }
    response = client.post("/api/v1/exposure-search/tasks", json=payload)
    assert response.status_code == 200
    assert response.json()["name"] == "Legacy Playwright Task"

def test_list_results():
    db = TestingSessionLocal()
    task = ExposureSearchTask(name="Result Task", org_keywords=[], title_keywords=[], url_keywords=[], file_types=[], sources=[])
    db.add(task)
    db.commit()
    
    result = ExposureSearchResult(task_id=task.id, source="bing", query="q", title="T", url="http://example.com/api-test")
    db.add(result)
    db.commit()
    task_id = task.id
    db.close()

    response = client.get(f"/api/v1/exposure-search/tasks/{task_id}/results")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_list_results_returns_office_preview_url_for_xlsx():
    db = TestingSessionLocal()
    task = ExposureSearchTask(name="Preview Task", org_keywords=[], title_keywords=[], url_keywords=[], file_types=[], sources=[])
    db.add(task)
    db.commit()

    result = ExposureSearchResult(
        task_id=task.id,
        source="bing",
        query="q",
        title="Spreadsheet",
        url="https://www.wenda.edu.cn/xmtys/upload/file/20250507/20250507101341_60712.xlsx",
        file_type="xlsx",
    )
    db.add(result)
    db.commit()
    task_id = task.id
    db.close()

    response = client.get(f"/api/v1/exposure-search/tasks/{task_id}/results")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["preview_url"].startswith("https://view.officeapps.live.com/op/view.aspx?src=")


def test_list_results_returns_no_preview_url_for_regular_web_page():
    db = TestingSessionLocal()
    task = ExposureSearchTask(name="No Preview Task", org_keywords=[], title_keywords=[], url_keywords=[], file_types=[], sources=[])
    db.add(task)
    db.commit()

    result = ExposureSearchResult(
        task_id=task.id,
        source="bing",
        query="q",
        title="Portal",
        url="https://example.com/portal",
        file_type=None,
    )
    db.add(result)
    db.commit()
    task_id = task.id
    db.close()

    response = client.get(f"/api/v1/exposure-search/tasks/{task_id}/results")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["preview_url"] is None


@pytest.mark.asyncio
async def test_preview_text_file_rejects_localhost_targets():
    from app.api import exposure_search as exposure_search_api

    with pytest.raises(HTTPException) as exc_info:
        await exposure_search_api.preview_text_file("http://127.0.0.1/internal", "json")

    assert exc_info.value.status_code == 400

def test_confirm_import_logic():
    db = TestingSessionLocal()
    task = ExposureSearchTask(name="Import Task", org_keywords=[], title_keywords=[], url_keywords=[], file_types=[], sources=[])
    db.add(task)
    db.commit()
    
    # Web asset
    res1 = ExposureSearchResult(task_id=task.id, source="bing", query="q", title="Web", url="http://example.com/web", status="pending")
    # Document clue
    res2 = ExposureSearchResult(task_id=task.id, source="bing", query="q", title="Doc", url="http://example.com/a.pdf", file_type="pdf", status="pending")
    db.add_all([res1, res2])
    db.commit()
    
    res1_id = res1.id
    res2_id = res2.id
    task_id = task.id
    db.close()

    payload = {
        "ids": [res1_id, res2_id],
        "import_all_valid": False
    }
    
    with patch("app.api.exposure_search.save_assets") as mock_save:
        response = client.post(f"/api/v1/exposure-search/tasks/{task_id}/confirm-import", json=payload)
        assert response.status_code == 200
        
        # Verify save_assets called only for web asset
        assert mock_save.called
        records = mock_save.call_args[0][2]
        assert len(records) == 1
        assert records[0]["url"] == "http://example.com/web"

    # Verify status updates
    db = TestingSessionLocal()
    r1 = db.get(ExposureSearchResult, res1_id)
    r2 = db.get(ExposureSearchResult, res2_id)
    assert r1.status == "imported"
    assert r2.status == "valid" # Mark as valid clue, not imported as WebEndpoint
    db.close()


def test_confirm_import_marks_github_results_as_valid_clues():
    db = TestingSessionLocal()
    task = ExposureSearchTask(name="GitHub Clue Task", org_keywords=[], title_keywords=[], url_keywords=[], file_types=[], sources=[])
    db.add(task)
    db.commit()

    result = ExposureSearchResult(
        task_id=task.id,
        source="github",
        query="q",
        title="Repo",
        url="https://github.com/example/repo",
        status="pending",
    )
    db.add(result)
    db.commit()

    result_id = result.id
    task_id = task.id
    db.close()

    with patch("app.api.exposure_search.save_assets") as mock_save:
        response = client.post(
            f"/api/v1/exposure-search/tasks/{task_id}/confirm-import",
            json={"ids": [result_id], "import_all_valid": False},
        )
        assert response.status_code == 200
        mock_save.assert_not_called()

    db = TestingSessionLocal()
    refreshed = db.get(ExposureSearchResult, result_id)
    assert refreshed.status == "valid"
    assert refreshed.imported_asset_id is None
    db.close()


def test_confirm_import_backfills_imported_asset_ids_from_save_result():
    db = TestingSessionLocal()
    task = ExposureSearchTask(name="Import Asset Id Task", org_keywords=[], title_keywords=[], url_keywords=[], file_types=[], sources=[])
    db.add(task)
    db.commit()

    result = ExposureSearchResult(
        task_id=task.id,
        source="bing",
        query="q",
        title="Web",
        url="https://example.com/asset",
        status="valid",
    )
    db.add(result)
    db.commit()

    result_id = result.id
    task_id = task.id
    db.close()

    fake_save_result = MagicMock()
    fake_save_result.saved_asset_ids = [str(uuid.uuid4())]

    with patch("app.api.exposure_search.save_assets", return_value=fake_save_result):
        response = client.post(
            f"/api/v1/exposure-search/tasks/{task_id}/confirm-import",
            json={"ids": [result_id], "import_all_valid": False},
        )
        assert response.status_code == 200

    db = TestingSessionLocal()
    refreshed = db.get(ExposureSearchResult, result_id)
    assert refreshed.status == "imported"
    assert refreshed.imported_asset_id == fake_save_result.saved_asset_ids[0]
    db.close()


def test_list_tasks_upgrades_legacy_exposure_search_schema():
    db_dir = Path("backend/.test_tmp")
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / f"legacy_exposure_search_{uuid.uuid4().hex}.db"
    legacy_engine = create_engine(f"sqlite:///{db_path}")
    legacy_session_local = sessionmaker(bind=legacy_engine)

    with legacy_engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE exposure_search_tasks (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    org_keywords TEXT,
                    title_keywords TEXT,
                    url_keywords TEXT,
                    file_types TEXT,
                    sources TEXT,
                    query_plan TEXT,
                    status TEXT,
                    total_results INTEGER,
                    valid_count INTEGER,
                    ignored_count INTEGER,
                    imported_count INTEGER,
                    error_message TEXT,
                    created_at TEXT,
                    started_at TEXT,
                    finished_at TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO exposure_search_tasks (
                    id, name, org_keywords, title_keywords, url_keywords, file_types,
                    sources, query_plan, status, total_results, valid_count,
                    ignored_count, imported_count, error_message, created_at,
                    started_at, finished_at
                ) VALUES (
                    :task_id, 'legacy task', '[]', '[]', '[]', '[]', '[]', NULL,
                    'pending', 0, 0, 0, 0, NULL, '2026-05-04 11:00:00', NULL, NULL
                )
                """
            ),
            {"task_id": str(uuid.uuid4())},
        )

    original_override = app.dependency_overrides[get_db]

    def override_legacy_db():
        db = legacy_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_legacy_db
    try:
        response = client.get("/api/v1/exposure-search/tasks")
    finally:
        app.dependency_overrides[get_db] = original_override

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "legacy task"
    columns = {item["name"] for item in inspect(legacy_engine).get_columns("exposure_search_tasks")}
    assert "max_results" in columns
    assert "max_pages" in columns
    assert "only_documents" in columns
    assert "only_webpages" in columns


def test_get_task_returns_derived_progress_fields():
    db = TestingSessionLocal()
    task = ExposureSearchTask(
        name="Progress Task",
        org_keywords=[],
        title_keywords=[],
        url_keywords=[],
        file_types=[],
        sources=[],
        query_plan=[
            {"query": 'site:example.com "one"', "status": "completed", "results_count": 2},
            {"query": 'site:example.com "two"', "status": "running", "results_count": 1},
            {"query": 'site:example.com "three"', "status": "pending", "results_count": 0},
        ],
    )
    db.add(task)
    db.commit()
    task_id = task.id
    db.close()

    response = client.get(f"/api/v1/exposure-search/tasks/{task_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["current_query"] == 'site:example.com "two"'
    assert body["next_query"] == 'site:example.com "three"'
    assert body["completed_queries"] == 1
    assert body["total_queries"] == 3
    assert body["progress_percent"] == 33


def test_get_task_backfills_query_plan_results_count_from_results_table():
    db = TestingSessionLocal()
    task = ExposureSearchTask(
        name="Query Count Sync Task",
        org_keywords=[],
        title_keywords=[],
        url_keywords=[],
        file_types=[],
        sources=[],
        query_plan=[
            {"query": "q1", "status": "completed", "results_count": 0},
            {"query": "q2", "status": "completed", "results_count": 0},
        ],
    )
    db.add(task)
    db.commit()

    db.add_all([
        ExposureSearchResult(task_id=task.id, source="bing", query="q1", title="A", url="https://example.com/a"),
        ExposureSearchResult(task_id=task.id, source="bing", query="q1", title="B", url="https://example.com/b"),
        ExposureSearchResult(task_id=task.id, source="bing", query="q2", title="C", url="https://example.com/c"),
    ])
    db.commit()
    task_id = task.id
    db.close()

    response = client.get(f"/api/v1/exposure-search/tasks/{task_id}")
    assert response.status_code == 200
    body = response.json()
    counts = {item["query"]: item["results_count"] for item in body["query_plan"]}
    assert counts == {"q1": 2, "q2": 1}


def test_get_task_appends_missing_queries_from_results_table():
    db = TestingSessionLocal()
    task = ExposureSearchTask(
        name="Missing Query Sync Task",
        org_keywords=[],
        title_keywords=[],
        url_keywords=[],
        file_types=[],
        sources=[],
        query_plan=[
            {"query": "q1", "status": "completed", "results_count": 0},
        ],
    )
    db.add(task)
    db.commit()

    db.add_all([
        ExposureSearchResult(task_id=task.id, source="bing", query="q1", title="A", url="https://example.com/a"),
        ExposureSearchResult(task_id=task.id, source="manual", query="Manual Capture from test", title="B", url="https://example.com/b"),
    ])
    db.commit()
    task_id = task.id
    db.close()

    response = client.get(f"/api/v1/exposure-search/tasks/{task_id}")
    assert response.status_code == 200
    body = response.json()
    counts = {item["query"]: item["results_count"] for item in body["query_plan"]}
    assert counts == {"q1": 1, "Manual Capture from test": 1}


@pytest.mark.asyncio
async def test_retry_query_endpoint_invokes_single_query_retry():
    from app.api import exposure_search as exposure_search_api

    db = TestingSessionLocal()
    task = ExposureSearchTask(
        name="Retry Task",
        org_keywords=[],
        title_keywords=[],
        url_keywords=[],
        file_types=[],
        sources=["bing"],
        query_plan=[
            {"query": "q1", "status": "completed", "results_count": 1},
            {"query": "q2", "status": "failed", "results_count": 0, "error_message": "captcha"},
        ],
    )
    db.add(task)
    db.commit()
    task_id = task.id

    called = {}

    async def fake_retry_query(self, called_task_id, query):
        called["task_id"] = called_task_id
        called["query"] = query

    with patch.object(exposure_search_api.ExposureSearchService, "retry_query", fake_retry_query):
        response = await exposure_search_api.retry_query(
            task_id,
            exposure_search_api.RetryExposureQueryRequest(query="q2"),
            db,
        )

    assert response.id == task_id
    assert called == {"task_id": task_id, "query": "q2"}
    db.close()
