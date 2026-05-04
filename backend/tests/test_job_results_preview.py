from datetime import datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import jobs as jobs_api


class FakeObservationQuery:
    def __init__(self, observations):
        self.observations = observations

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return self.observations

    def count(self):
        return len(self.observations)


class FakeAssetQuery:
    def __init__(self, assets):
        self.assets = assets

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return list(self.assets.values())


class NarrowAssetQuery(FakeAssetQuery):
    def __init__(self, assets):
        super().__init__(assets)
        self.filtered = False

    def filter(self, *args, **kwargs):
        self.filtered = True
        return self

    def all(self):
        if not self.filtered:
            raise AssertionError("expected narrowed asset query")
        return super().all()


class FakeDb:
    def __init__(self, job, observations, assets):
        self.job = job
        self.observations = observations
        self.assets = assets

    def query(self, model):
        if model is jobs_api.SourceObservation:
            return FakeObservationQuery(self.observations)
        if model is jobs_api.WebEndpoint:
            return FakeAssetQuery(self.assets)
        raise AssertionError(f"unexpected model: {model}")

    def get(self, model, record_id):
        if model is jobs_api.CollectJob:
            return self.job if record_id == self.job.id else None
        return self.assets.get(record_id)


class NarrowFakeDb(FakeDb):
    def query(self, model):
        if model is jobs_api.SourceObservation:
            return FakeObservationQuery(self.observations)
        if model is jobs_api.WebEndpoint:
            return NarrowAssetQuery(self.assets)
        raise AssertionError(f"unexpected model: {model}")


def make_fake_job(job_id: str = "job-1"):
    return SimpleNamespace(
        id=job_id,
        job_name="demo job",
        status="success",
        sources=["fofa"],
        query_payload={"queries": []},
        progress=100,
        auto_verify=False,
        started_at=None,
        finished_at=None,
        success_count=1,
        failed_count=0,
        duplicate_count=0,
        total_count=1,
        dedup_strategy="skip",
        field_mapping={},
        created_at=datetime(2026, 4, 21, 12, 0, 0),
        error_message=None,
    )


app = FastAPI()
app.include_router(jobs_api.router, prefix="/api/v1/jobs")
client = TestClient(app)


def test_get_job_results_returns_assets_from_observations():
    observation = SimpleNamespace(raw_payload={"web_endpoint_id": "asset-1"}, created_at=None)
    asset = SimpleNamespace(
        id="asset-1",
        normalized_url="https://example.com",
        title="Example",
        status_code=200,
        screenshot_status="none",
        label_status="none",
        verified=False,
        source_meta={"source": "fofa", "host": "example.com"},
        first_seen_at=None,
        last_seen_at=None,
        screenshots=[],
        domain="example.com",
        host=SimpleNamespace(ip="1.1.1.1"),
        service=SimpleNamespace(port=443, host=SimpleNamespace(ip="1.1.1.1")),
    )
    fake_db = FakeDb(make_fake_job(), [observation], {"asset-1": asset})
    app.dependency_overrides[jobs_api.get_db] = lambda: fake_db
    try:
        response = client.get("/api/v1/jobs/job-1/results")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["url"] == "https://example.com"
    assert body["items"][0]["domain"] == "example.com"
    assert body["items"][0]["ip"] == "1.1.1.1"
    assert body["items"][0]["port"] == 443
    assert body["total"] == 1


def test_get_job_results_can_fallback_to_normalized_url():
    observation = SimpleNamespace(raw_payload={"normalized_url": "https://example.com"}, created_at=None)
    asset = SimpleNamespace(
        id="asset-1",
        normalized_url="https://example.com",
        title="Example",
        status_code=200,
        screenshot_status="none",
        label_status="none",
        verified=False,
        source_meta={"source": "fofa", "host": "example.com"},
        first_seen_at=None,
        last_seen_at=None,
        screenshots=[],
        domain="example.com",
        host=SimpleNamespace(ip="1.1.1.1"),
        service=SimpleNamespace(port=443, host=SimpleNamespace(ip="1.1.1.1")),
    )
    fake_db = FakeDb(make_fake_job(), [observation], {"asset-1": asset})
    app.dependency_overrides[jobs_api.get_db] = lambda: fake_db
    try:
        response = client.get("/api/v1/jobs/job-1/results")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == "asset-1"


def test_get_job_results_keeps_observation_order_after_batch_lookup():
    observations = [
        SimpleNamespace(raw_payload={"web_endpoint_id": "asset-2"}, created_at=None),
        SimpleNamespace(raw_payload={"web_endpoint_id": "asset-1"}, created_at=None),
    ]
    assets = {
        "asset-1": SimpleNamespace(
            id="asset-1",
            normalized_url="https://first.example.com",
            title="First",
            status_code=200,
            screenshot_status="none",
            label_status="none",
            verified=False,
            source_meta={"source": "fofa", "host": "first.example.com"},
            first_seen_at=None,
            last_seen_at=None,
            screenshots=[],
            domain="first.example.com",
            host=SimpleNamespace(ip="1.1.1.1"),
            service=SimpleNamespace(port=443, host=SimpleNamespace(ip="1.1.1.1")),
        ),
        "asset-2": SimpleNamespace(
            id="asset-2",
            normalized_url="https://second.example.com",
            title="Second",
            status_code=200,
            screenshot_status="none",
            label_status="none",
            verified=False,
            source_meta={"source": "fofa", "host": "second.example.com"},
            first_seen_at=None,
            last_seen_at=None,
            screenshots=[],
            domain="second.example.com",
            host=SimpleNamespace(ip="2.2.2.2"),
            service=SimpleNamespace(port=443, host=SimpleNamespace(ip="2.2.2.2")),
        ),
    }
    fake_db = FakeDb(make_fake_job(), observations, assets)
    app.dependency_overrides[jobs_api.get_db] = lambda: fake_db
    try:
        response = client.get("/api/v1/jobs/job-1/results")
    finally:
        app.dependency_overrides.clear()



def test_get_collect_job_returns_detail_payload():
    fake_db = FakeDb(make_fake_job(), [], {})
    app.dependency_overrides[jobs_api.get_db] = lambda: fake_db
    try:
        response = client.get("/api/v1/jobs/job-1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()


def test_get_job_results_uses_narrowed_asset_lookup_query():
    observation = SimpleNamespace(raw_payload={"normalized_url": "https://example.com"}, created_at=None)
    asset = SimpleNamespace(
        id="asset-1",
        normalized_url="https://example.com",
        title="Example",
        status_code=200,
        screenshot_status="none",
        label_status="none",
        verified=False,
        source_meta={"source": "fofa", "host": "example.com"},
        first_seen_at=None,
        last_seen_at=None,
        screenshots=[],
        domain="example.com",
        host=SimpleNamespace(ip="1.1.1.1"),
        service=SimpleNamespace(port=443, host=SimpleNamespace(ip="1.1.1.1")),
    )
    fake_db = NarrowFakeDb(make_fake_job(), [observation], {"asset-1": asset})
    app.dependency_overrides[jobs_api.get_db] = lambda: fake_db
    try:
        response = client.get("/api/v1/jobs/job-1/results")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == "asset-1"



def test_get_job_results_can_match_by_fallback_url():
    observation = SimpleNamespace(raw_payload={"fallback_url": "https://example.com/"}, created_at=None)
    asset = SimpleNamespace(
        id="asset-1",
        normalized_url="https://example.com/",
        title="Example",
        status_code=200,
        screenshot_status="none",
        label_status="none",
        verified=False,
        source_meta={"source": "fofa", "host": "example.com"},
        first_seen_at=None,
        last_seen_at=None,
        screenshots=[],
        domain="example.com",
        host=SimpleNamespace(ip="1.1.1.1"),
        service=SimpleNamespace(port=443, host=SimpleNamespace(ip="1.1.1.1")),
    )
    fake_db = FakeDb(make_fake_job(), [observation], {"asset-1": asset})
    app.dependency_overrides[jobs_api.get_db] = lambda: fake_db
    try:
        response = client.get("/api/v1/jobs/job-1/results")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == "asset-1"



def test_get_job_results_can_match_by_source_meta_ip_port_without_relations():
    observation = SimpleNamespace(raw_payload={"ip": "1.1.1.1", "port": 443}, created_at=None)
    asset = SimpleNamespace(
        id="asset-1",
        normalized_url="https://example.com/",
        title="Example",
        status_code=200,
        screenshot_status="none",
        label_status="none",
        verified=False,
        source_meta={"source": "fofa", "host": "example.com", "ip": "1.1.1.1", "port": 443},
        first_seen_at=None,
        last_seen_at=None,
        screenshots=[],
        domain=None,
        host=None,
        service=None,
    )
    fake_db = FakeDb(make_fake_job(), [observation], {"asset-1": asset})
    app.dependency_overrides[jobs_api.get_db] = lambda: fake_db
    try:
        response = client.get("/api/v1/jobs/job-1/results")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == "asset-1"



def test_get_job_results_can_match_by_observation_source_record_id():
    source_record_id = "csv_import:host-port:demo.example.com:443"
    observation = SimpleNamespace(source_record_id=source_record_id, raw_payload={}, created_at=None)
    asset = SimpleNamespace(
        id="asset-1",
        normalized_url="https://demo.example.com/",
        title="Example",
        status_code=200,
        screenshot_status="none",
        label_status="none",
        verified=False,
        source_meta={"source": "csv_import", "source_record_id": source_record_id, "host": "demo.example.com", "port": 443},
        first_seen_at=None,
        last_seen_at=None,
        screenshots=[],
        domain="demo.example.com",
        host=None,
        service=None,
    )
    fake_db = FakeDb(make_fake_job(), [observation], {"asset-1": asset})
    app.dependency_overrides[jobs_api.get_db] = lambda: fake_db
    try:
        response = client.get("/api/v1/jobs/job-1/results")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == "asset-1"



def test_get_job_results_observation_fallback_uses_source_record_id():
    source_record_id = "hunter:ip-port:1.1.1.1:22"
    observation = SimpleNamespace(source_record_id=source_record_id, raw_payload={"ip": "1.1.1.1", "port": 22}, created_at=None)
    fake_db = FakeDb(make_fake_job(), [observation], {})
    app.dependency_overrides[jobs_api.get_db] = lambda: fake_db
    try:
        response = client.get("/api/v1/jobs/job-1/results")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == source_record_id



def test_summarize_task_details_extracts_stage_last_errors():
    job = make_fake_job()
    job.auto_verify = True
    fake_db = FakeDb(job, [], {})

    details = jobs_api._summarize_task_details(
        job,
        "\n".join(
            [
                "Auto verify start assets=2",
                "Verify failed asset_id=asset-1 url=https://example.com reason=请求超时",
                "Screenshot failed asset_id=asset-1 reason=missing-file",
                "Auto verify finished verify_success=0 verify_failed=1 screenshot_success=0 screenshot_failed=1",
            ]
        ),
        fake_db,
        result_asset_count=0,
    )

    assert details.post_process.verify.last_error == "请求超时"
    assert details.post_process.screenshot.last_error == "missing-file"



def test_summarize_task_details_marks_verify_stage_finished_without_waiting_for_screenshot():

    job = make_fake_job()
    job.auto_verify = True
    fake_db = FakeDb(job, [], {})

    details = jobs_api._summarize_task_details(
        job,
        "\n".join(
            [
                "Auto verify start assets=1",
                "Verify success asset_id=asset-1 url=https://example.com status=200",
                "Verify post-process finished success=1 failed=0",
            ]
        ),
        fake_db,
        result_asset_count=0,
    )

    assert details.post_process.verify.state == "success"
    assert details.post_process.screenshot.state == "pending"
