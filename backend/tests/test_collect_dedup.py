from datetime import datetime
from types import SimpleNamespace

from app.models.asset import WebEndpoint
from app.services.collectors.dedup import touch_existing_web_endpoint
from app.tasks import collect


class DuplicateQuery:
    def __init__(self, web):
        self.web = web

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.web


class DuplicateDb:
    def __init__(self, web):
        self.web = web
        self.commit_count = 0
        self.flushed = False

    def query(self, model):
        assert model is collect.WebEndpoint
        return DuplicateQuery(self.web)

    def commit(self):
        self.commit_count += 1

    def flush(self):
        self.flushed = True

    def rollback(self):
        raise AssertionError("rollback should not run for duplicate rows")


def test_touch_existing_web_endpoint_only_updates_seen_timestamps():
    original_first_seen = datetime(2026, 4, 18, 8, 0, 0)
    observed_at = datetime(2026, 4, 19, 9, 30, 0)
    web = WebEndpoint(
        normalized_url="https://example.com",
        normalized_url_hash="hash-1",
        title="Keep title",
        status_code=200,
        domain="example.com",
        first_seen_at=original_first_seen,
        last_seen_at=original_first_seen,
    )

    touch_existing_web_endpoint(web, observed_at)

    assert web.first_seen_at == original_first_seen
    assert web.last_seen_at == observed_at
    assert web.title == "Keep title"
    assert web.status_code == 200
    assert web.domain == "example.com"


def test_touch_existing_web_endpoint_backfills_missing_first_seen():
    observed_at = datetime(2026, 4, 19, 9, 30, 0)
    web = WebEndpoint(
        normalized_url="https://example.com",
        normalized_url_hash="hash-2",
        first_seen_at=None,
        last_seen_at=None,
    )

    touch_existing_web_endpoint(web, observed_at)

    assert web.first_seen_at == observed_at
    assert web.last_seen_at == observed_at


def test_save_assets_touches_duplicate_without_overwriting_fields():
    existing = WebEndpoint(
        normalized_url="https://example.com",
        normalized_url_hash=collect.build_url_hash("https://example.com"),
        title="Keep me",
        status_code=200,
        first_seen_at=datetime(2026, 4, 18, 8, 0, 0),
        last_seen_at=datetime(2026, 4, 18, 8, 0, 0),
    )
    db = DuplicateDb(existing)
    job = SimpleNamespace(success_count=0, duplicate_count=0, failed_count=0, dedup_strategy="overwrite")

    collect.save_assets(
        db,
        job,
        [{"url": "https://example.com", "ip": "1.1.1.1", "port": 443, "title": "Replace me"}],
        "fofa",
    )

    assert job.duplicate_count == 1
    assert existing.title == "Keep me"
    assert existing.status_code == 200
    assert existing.last_seen_at > datetime(2026, 4, 18, 8, 0, 0)
