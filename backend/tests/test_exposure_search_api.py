import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, JSON, StaticPool
from sqlalchemy.orm import sessionmaker
import sqlalchemy.dialects.postgresql as postgresql

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
        "auto_run": False
    }
    response = client.post("/api/v1/exposure-search/tasks", json=payload)
    assert response.status_code == 200
    assert response.json()["name"] == "API Test Task"

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
