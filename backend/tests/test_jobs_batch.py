from datetime import datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import jobs as jobs_api
from app.models import CollectJob, JobPendingAsset


class FakeQuery:
    def __init__(self, items):
        self.items = items

    def filter(self, *criteria):
        filtered = list(self.items)
        for criterion in criteria:
            left = getattr(criterion, "left", None)
            right = getattr(criterion, "right", None)
            key = getattr(left, "key", None)
            value = getattr(right, "value", None)
            if key is None:
                continue
            filtered = [item for item in filtered if getattr(item, key, None) == value]
        self.items = filtered
        return self

    def order_by(self, *args, **kwargs):
        return self

    def offset(self, value):
        self.items = self.items[value:]
        return self

    def limit(self, value):
        self.items = self.items[:value]
        return self

    def count(self):
        return len(self.items)

    def all(self):
        return list(self.items)

    def delete(self, synchronize_session=False):
        count = len(self.items)
        self.items.clear()
        return count


class FakeDb:
    def __init__(self, jobs, pending_assets):
        self.jobs = {job.id: job for job in jobs}
        self.pending_assets = pending_assets
        self.commits = 0
        self.deleted = []

    @property
    def bind(self):
        return None

    def get(self, model, record_id):
        if model is CollectJob:
            return self.jobs.get(record_id)
        return None

    def query(self, model):
        if model is JobPendingAsset:
            return FakeQuery(self.pending_assets)
        raise AssertionError(f"unexpected model: {model}")

    def delete(self, item):
        self.deleted.append(item.id)
        self.jobs.pop(item.id, None)

    def commit(self):
        self.commits += 1


app = FastAPI()
app.include_router(jobs_api.router, prefix="/api/v1/jobs")
client = TestClient(app)


def make_job(job_id: str, status: str = "pending_import"):
    return SimpleNamespace(
        id=job_id,
        job_name=f"job-{job_id}",
        status=status,
        sources=["hunter"],
        query_payload={"queries": []},
        progress=100,
        success_count=0,
        failed_count=0,
        duplicate_count=0,
        total_count=0,
        dedup_strategy="skip",
        field_mapping={},
        auto_verify=False,
        created_at=datetime(2026, 4, 28, 0, 0, 0),
        started_at=None,
        finished_at=None,
        error_message=None,
    )


def make_pending_asset(item_id: str, job_id: str):
    return SimpleNamespace(
        id=item_id,
        job_id=job_id,
        source="hunter",
        raw_data={"url": "https://example.com", "raw": item_id},
        mapped_data={"url": "https://example.com", "raw_data": {"url": "https://example.com"}},
        status="pending",
        created_at=datetime(2026, 4, 28, 0, 0, 0),
        imported_at=None,
    )


def test_get_pending_assets_returns_items():
    fake_db = FakeDb([make_job("job-1")], [make_pending_asset("pending-1", "job-1")])
    app.dependency_overrides[jobs_api.get_db] = lambda: fake_db
    try:
        response = client.get("/api/v1/jobs/job-1/pending-assets")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == "job-1"
    assert body["total"] == 1
    assert body["items"][0]["id"] == "pending-1"


def test_confirm_import_marks_items_imported_and_updates_job(monkeypatch):
    job = make_job("job-2")
    pending_assets = [make_pending_asset("pending-1", "job-2"), make_pending_asset("pending-2", "job-2")]
    fake_db = FakeDb([job], pending_assets)

    def fake_save_assets(_db, target_job, records, source_name):
        target_job.success_count += len(records)
        target_job.total_count += len(records)

    monkeypatch.setattr(jobs_api, "save_assets", fake_save_assets)
    app.dependency_overrides[jobs_api.get_db] = lambda: fake_db
    try:
        response = client.post("/api/v1/jobs/job-2/confirm-import", json={"import_all": True})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["success"] == 2
    assert body["status"] == "imported"
    assert all(item.status == "imported" for item in pending_assets)


def test_discard_import_marks_pending_items_discarded():
    job = make_job("job-3")
    pending_assets = [make_pending_asset("pending-1", "job-3")]
    fake_db = FakeDb([job], pending_assets)
    app.dependency_overrides[jobs_api.get_db] = lambda: fake_db
    try:
        response = client.post("/api/v1/jobs/job-3/discard-import")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["discarded"] == 1
    assert body["status"] == "discarded"
    assert pending_assets[0].status == "discarded"


def test_batch_delete_jobs_reports_partial_failures():
    fake_db = FakeDb([make_job("job-4", "imported")], [])
    app.dependency_overrides[jobs_api.get_db] = lambda: fake_db
    try:
        response = client.post("/api/v1/jobs/batch-delete", json={"ids": ["job-4", "missing"]})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["success"] == 1
    assert body["failed"] == 1


def test_batch_start_jobs_rejects_invalid_status():
    fake_db = FakeDb([make_job("job-5", "running")], [])
    app.dependency_overrides[jobs_api.get_db] = lambda: fake_db
    try:
        response = client.post("/api/v1/jobs/batch-start", json={"ids": ["job-5"]})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["success"] == 0
    assert body["failed"] == 1
