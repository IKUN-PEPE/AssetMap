import asyncio
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import Base
from app.models.exposure_search import ExposureSearchResult, ExposureSearchTask
from app.services.exposure_search import ExposureSearchService
from app.services.exposure_search.risk_classifier import RiskClassifier


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.mark.asyncio
async def test_handle_manual_clue(db: Session):
    import uuid

    task_id = str(uuid.uuid4())
    task = ExposureSearchTask(
        id=task_id,
        name="Test Manual Capture",
        org_keywords=["ExampleOrg"],
        title_keywords=[],
        url_keywords=[],
        file_types=[],
        sources=["manual"],
    )
    db.add(task)
    db.commit()

    service = ExposureSearchService(db=db)
    classifier = RiskClassifier(org_keywords=["ExampleOrg"])

    clue_data = {
        "title": "Sensitive ExampleOrg Data",
        "url": "http://example.com/sensitive",
        "snippet": "Internal document for ExampleOrg",
        "source_page": "https://www.bing.com/search?q=ExampleOrg",
        "query": '"ExampleOrg" "login"',
    }

    await service._handle_manual_clue(task.id, classifier, clue_data, db)

    result = db.query(ExposureSearchResult).filter(ExposureSearchResult.url == clue_data["url"]).first()
    assert result is not None
    assert result.task_id == task.id
    assert result.source == "manual"
    assert result.query == '"ExampleOrg" "login"'
    assert result.status == "valid"
    assert "Sensitive" in result.title
    assert "exampleorg" in result.matched_keywords

    db.refresh(task)
    assert task.total_results == 1
    assert task.valid_count == 1

    await service._handle_manual_clue(task.id, classifier, clue_data, db)
    db.refresh(task)
    assert task.total_results == 1


class _FakeProvider:
    name = "bing"

    def __init__(self, item):
        self.item = item
        self.calls = []

    async def search(self, query: str, max_results: int, max_pages: int, **kwargs):
        self.calls.append((query, max_results, max_pages))
        return [self.item]


class _MultiItemProvider:
    def __init__(self, name: str, items):
        self.name = name
        self.items = items
        self.calls = []

    async def search(self, query: str, max_results: int, max_pages: int, **kwargs):
        self.calls.append((query, max_results, max_pages))
        return list(self.items)


@pytest.mark.asyncio
async def test_run_task_uses_task_limits_and_syncs_final_counts(monkeypatch, db: Session):
    import uuid

    task = ExposureSearchTask(
        id=str(uuid.uuid4()),
        name="Run Task",
        org_keywords=["ExampleOrg"],
        title_keywords=[],
        url_keywords=[],
        file_types=[],
        sources=["bing"],
        max_results=7,
        max_pages=4,
    )
    db.add(task)
    db.commit()

    service = ExposureSearchService(db=db)
    item = type(
        "Item",
        (),
        {
            "source": "bing",
            "title": "ExampleOrg Portal",
            "url": "https://example.com/portal",
            "snippet": "login",
            "raw_payload": {},
        },
    )()
    provider = _FakeProvider(item)

    monkeypatch.setattr("app.services.exposure_search.QueryBuilder.build_queries", lambda self: ["query-1"])
    monkeypatch.setattr("app.services.exposure_search.BingProvider", lambda _pw_client: provider)

    async def fake_stop():
        return None

    monkeypatch.setattr(service.pw_client, "stop", fake_stop)

    async def fake_manual_clue(task_id, classifier, data, _unused_db=None):
        db.add(
            ExposureSearchResult(
                task_id=task_id,
                source="manual",
                query="manual",
                title=data["title"],
                url=data["url"],
                snippet=data.get("snippet"),
                risk_tags=[],
                matched_keywords=[],
                raw_payload={},
                status="valid",
            )
        )
        db.commit()

    monkeypatch.setattr(service, "_handle_manual_clue", fake_manual_clue)

    await service._handle_manual_clue(
        task.id,
        RiskClassifier(org_keywords=["ExampleOrg"]),
        {"title": "Manual", "url": "https://manual.example.com", "snippet": "manual"},
        db,
    )
    await service.run_task(task.id)

    refreshed_task = db.query(ExposureSearchTask).filter(ExposureSearchTask.id == task.id).first()
    assert provider.calls == [("query-1", 7, 4)]
    assert refreshed_task.status == "completed"
    assert refreshed_task.total_results == 2


@pytest.mark.asyncio
async def test_run_task_enforces_global_max_results_across_providers(monkeypatch, db: Session):
    import uuid

    task = ExposureSearchTask(
        id=str(uuid.uuid4()),
        name="Global Limit Task",
        org_keywords=["ExampleOrg"],
        title_keywords=[],
        url_keywords=[],
        file_types=[],
        sources=["bing", "google"],
        max_results=2,
        max_pages=1,
    )
    db.add(task)
    db.commit()

    service = ExposureSearchService(db=db)
    provider_a = _MultiItemProvider(
        "bing",
        [
            type("Item", (), {"source": "bing", "title": "A1", "url": "https://example.com/a1", "snippet": "", "raw_payload": {}})(),
            type("Item", (), {"source": "bing", "title": "A2", "url": "https://example.com/a2", "snippet": "", "raw_payload": {}})(),
        ],
    )
    provider_b = _MultiItemProvider(
        "google",
        [
            type("Item", (), {"source": "google", "title": "B1", "url": "https://example.com/b1", "snippet": "", "raw_payload": {}})(),
            type("Item", (), {"source": "google", "title": "B2", "url": "https://example.com/b2", "snippet": "", "raw_payload": {}})(),
        ],
    )

    monkeypatch.setattr("app.services.exposure_search.QueryBuilder.build_queries", lambda self: ["query-1"])
    monkeypatch.setattr("app.services.exposure_search.BingProvider", lambda _pw_client: provider_a)
    monkeypatch.setattr("app.services.exposure_search.GoogleProvider", lambda _pw_client: provider_b)

    async def fake_stop():
        return None

    monkeypatch.setattr(service.pw_client, "stop", fake_stop)

    await service.run_task(task.id)

    rows = (
        db.query(ExposureSearchResult)
        .filter(ExposureSearchResult.task_id == task.id)
        .order_by(ExposureSearchResult.created_at.asc())
        .all()
    )
    assert len(rows) == 2
    assert {row.url for row in rows} == {"https://example.com/a1", "https://example.com/a2"}
    assert provider_a.calls == [("query-1", 2, 1)]
    assert provider_b.calls == []


@pytest.mark.asyncio
async def test_run_task_headless_updates_query_plan_for_each_query(monkeypatch, db: Session):
    import uuid

    task = ExposureSearchTask(
        id=str(uuid.uuid4()),
        name="Headless Query Plan Task",
        org_keywords=["ExampleOrg"],
        title_keywords=[],
        url_keywords=[],
        file_types=[],
        sources=["bing"],
        max_results=5,
        max_pages=1,
    )
    db.add(task)
    db.commit()

    service = ExposureSearchService(db=db)
    provider = _FakeProvider(
        type(
            "Item",
            (),
            {"source": "bing", "title": "Portal", "url": "https://example.com/portal", "snippet": "", "raw_payload": {}},
        )()
    )

    monkeypatch.setattr("app.services.exposure_search.QueryBuilder.build_queries", lambda self: ["query-1", "query-2"])
    monkeypatch.setattr("app.services.exposure_search.BingProvider", lambda _pw_client: provider)

    async def fake_stop():
        return None

    monkeypatch.setattr(service.pw_client, "stop", fake_stop)

    await service.run_task(task.id)

    refreshed_task = db.query(ExposureSearchTask).filter(ExposureSearchTask.id == task.id).first()
    assert refreshed_task is not None
    assert [item["status"] for item in refreshed_task.query_plan] == ["completed", "completed"]
    assert sorted(item["results_count"] for item in refreshed_task.query_plan) == [0, 1]


@pytest.mark.asyncio
async def test_run_task_headless_can_run_queries_concurrently_with_isolated_sessions(monkeypatch, db: Session):
    import uuid

    task = ExposureSearchTask(
        id=str(uuid.uuid4()),
        name="Concurrent Headless Task",
        org_keywords=["ExampleOrg"],
        title_keywords=[],
        url_keywords=[],
        file_types=[],
        sources=["bing"],
        max_results=5,
        max_pages=1,
    )
    db.add(task)
    db.commit()

    service = ExposureSearchService(db=db)
    provider = _FakeProvider(
        type(
            "Item",
            (),
            {"source": "bing", "title": "Portal", "url": "https://example.com/portal", "snippet": "", "raw_payload": {}},
        )()
    )

    entered_queries = []
    release_gate = asyncio.Event()

    async def blocking_search(query: str, max_results: int, max_pages: int, **kwargs):
        entered_queries.append(query)
        if len(entered_queries) >= 2:
            release_gate.set()
        await release_gate.wait()
        return [provider.item]

    provider.search = blocking_search

    monkeypatch.setattr("app.services.exposure_search.QueryBuilder.build_queries", lambda self: ["query-1", "query-2"])
    monkeypatch.setattr("app.services.exposure_search.BingProvider", lambda _pw_client: provider)

    async def fake_stop():
        return None

    monkeypatch.setattr(service.pw_client, "stop", fake_stop)

    await service.run_task(task.id)

    assert set(entered_queries) == {"query-1", "query-2"}
    assert len(entered_queries) == 2


@pytest.mark.asyncio
async def test_request_intervention_returns_finish_when_finish_signal_is_received(monkeypatch):
    service = ExposureSearchService(headless=False)

    class FakePage:
        url = "https://example.com/captcha"

    monkeypatch.setattr(service, "stop_check", lambda _task_id, _db: False)

    async def trigger_finish():
        await asyncio.sleep(0.02)
        await service._handle_finish_signal()

    trigger = asyncio.create_task(trigger_finish())
    result = await service.request_intervention(FakePage(), "task-1", object())
    await trigger

    assert result == "finish"


def test_build_task_schema_derives_progress_fields():
    task = ExposureSearchTask(
        id="task-1",
        name="Derived Progress",
        org_keywords=[],
        title_keywords=[],
        url_keywords=[],
        file_types=[],
        sources=[],
        query_plan=[
            {"query": "q1", "status": "completed", "results_count": 1},
            {"query": "q2", "status": "running", "results_count": 0},
            {"query": "q3", "status": "pending", "results_count": 0},
        ],
        max_results=10,
        max_pages=2,
        only_documents=False,
        only_webpages=False,
        status="running",
        total_results=1,
        valid_count=0,
        ignored_count=0,
        imported_count=0,
        created_at=datetime(2026, 5, 4, 12, 0, 0),
    )

    payload = ExposureSearchService.build_task_schema(task)

    assert payload.current_query == "q2"
    assert payload.next_query == "q3"
    assert payload.completed_queries == 1
    assert payload.total_queries == 3
    assert payload.progress_percent == 33


@pytest.mark.asyncio
async def test_run_task_records_query_error_in_query_plan(monkeypatch, db: Session):
    import uuid

    task = ExposureSearchTask(
        id=str(uuid.uuid4()),
        name="Query Failure Task",
        org_keywords=["ExampleOrg"],
        title_keywords=[],
        url_keywords=[],
        file_types=[],
        sources=["bing"],
        max_results=5,
        max_pages=1,
    )
    db.add(task)
    db.commit()

    service = ExposureSearchService(db=db)

    class FailingProvider:
        name = "bing"

        async def search(self, *args, **kwargs):
            raise RuntimeError("captcha blocked")

    monkeypatch.setattr("app.services.exposure_search.QueryBuilder.build_queries", lambda self: ["query-1"])
    monkeypatch.setattr("app.services.exposure_search.BingProvider", lambda _pw_client: FailingProvider())

    async def fake_stop():
        return None

    monkeypatch.setattr(service.pw_client, "stop", fake_stop)

    await service.run_task(task.id)

    refreshed_task = db.query(ExposureSearchTask).filter(ExposureSearchTask.id == task.id).first()
    assert refreshed_task is not None
    assert refreshed_task.query_plan[0]["status"] == "failed"
    assert "captcha blocked" in refreshed_task.query_plan[0]["error_message"]
    assert refreshed_task.query_plan[0]["error_category"] == "验证码/风控"
