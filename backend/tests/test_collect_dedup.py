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
        self.added = []

    def query(self, model):
        assert model is collect.WebEndpoint
        return DuplicateQuery(self.web)

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.commit_count += 1

    def flush(self):
        self.flushed = True

    def rollback(self):
        raise AssertionError("rollback should not run for duplicate rows")


class ObservationOnlyDb:
    def __init__(self):
        self.added = []

    def query(self, _model):
        return DuplicateQuery(None)

    def add(self, item):
        self.added.append(item)

    def flush(self):
        return None

    def rollback(self):
        raise AssertionError("rollback should not run for observation-only rows")


class IterAssetsQuery:
    def __init__(self, items):
        self.items = items

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return list(self.items)


class IterAssetsDb:
    def __init__(self, fallback_assets):
        self.fallback_assets = fallback_assets

    def query(self, model):
        assert model is collect.WebEndpoint
        return IterAssetsQuery(self.fallback_assets)


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


class FallbackLookupQuery:
    def __init__(self, db):
        self.db = db
        self.criteria = []

    def filter(self, *args, **kwargs):
        self.criteria.extend(args)
        return self

    def outerjoin(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        for criterion in self.criteria:
            right = getattr(criterion, "right", None)
            value = getattr(right, "value", None)
            if self.db.match_hash and value == self.db.match_hash:
                return self.db.web
        return None


class FallbackLookupDb:
    def __init__(self, web, match_hash: str | None = None):
        self.web = web
        self.match_hash = match_hash

    def query(self, model):
        assert model is collect.WebEndpoint
        return FallbackLookupQuery(self)


def test_resolve_asset_identity_preserves_explicit_default_https_port_in_normalized_url():
    resolved = collect._resolve_asset_identity(
        {
            "host": "example.com",
            "port": 443,
            "protocol": "https",
        }
    )

    assert resolved["normalized_url"] == "https://example.com:443/"


def test_resolve_asset_identity_normalizes_entry_url_case_and_strips_auth():
    resolved = collect._resolve_asset_identity(
        {
            "url": "HTTPS://User:Pass@EXAMPLE.com/login",
            "protocol": "https",
        }
    )

    assert resolved["normalized_url"] == "https://example.com/login"


def test_find_existing_web_endpoint_does_not_fallback_to_host_port_for_explicit_443_variant():
    existing = WebEndpoint(
        normalized_url="https://example.com",
        normalized_url_hash=collect.build_url_hash("https://example.com"),
        first_seen_at=datetime(2026, 4, 18, 8, 0, 0),
        last_seen_at=datetime(2026, 4, 18, 8, 0, 0),
    )
    db = FallbackLookupDb(existing, match_hash=None)

    result = collect._find_existing_web_endpoint(
        db,
        {
            "normalized_url": "https://example.com:443",
            "host": "example.com",
            "domain": "example.com",
            "port": 443,
            "ip": None,
        },
    )

    assert result is None


def test_find_existing_web_endpoint_matches_same_site_different_url_variants_by_entry_url():
    entry_hash = collect.build_url_hash("https://example.com/")
    existing = WebEndpoint(
        normalized_url="https://example.com/",
        normalized_url_hash=entry_hash,
        first_seen_at=datetime(2026, 4, 18, 8, 0, 0),
        last_seen_at=datetime(2026, 4, 18, 8, 0, 0),
        source_meta={"entry_url": "https://example.com/", "entry_url_hash": entry_hash},
    )
    db = FallbackLookupDb(existing, match_hash=entry_hash)

    result = collect._find_existing_web_endpoint(
        db,
        {
            "normalized_url": "https://example.com/login",
            "entry_url": "https://example.com/",
            "entry_url_hash": entry_hash,
            "host": "example.com",
            "domain": "example.com",
            "port": 443,
            "ip": None,
        },
    )

    assert result is existing


def test_find_existing_web_endpoint_distinguishes_scheme_and_port_by_entry_url():
    entry_hash = collect.build_url_hash("https://example.com/")
    existing = WebEndpoint(
        normalized_url="https://example.com/",
        normalized_url_hash=entry_hash,
        first_seen_at=datetime(2026, 4, 18, 8, 0, 0),
        last_seen_at=datetime(2026, 4, 18, 8, 0, 0),
        source_meta={"entry_url": "https://example.com/", "entry_url_hash": entry_hash},
    )
    db = FallbackLookupDb(existing, match_hash=entry_hash)

    different_scheme = collect._find_existing_web_endpoint(
        db,
        {
            "normalized_url": "http://example.com/",
            "entry_url": "http://example.com/",
            "entry_url_hash": collect.build_url_hash("http://example.com/"),
            "host": "example.com",
            "domain": "example.com",
            "port": 80,
            "ip": None,
        },
    )
    different_port = collect._find_existing_web_endpoint(
        db,
        {
            "normalized_url": "https://example.com:8443/",
            "entry_url": "https://example.com:8443/",
            "entry_url_hash": collect.build_url_hash("https://example.com:8443/"),
            "host": "example.com",
            "domain": "example.com",
            "port": 8443,
            "ip": None,
        },
    )

    assert different_scheme is None
    assert different_port is None


def test_save_assets_stores_exact_url_hash_separately_from_entry_hash():
    db = ObservationOnlyDb()
    job = SimpleNamespace(success_count=0, duplicate_count=0, failed_count=0, dedup_strategy="overwrite", id="job-exact")

    collect.save_assets(
        db,
        job,
        [{"url": "https://example.com/login?next=/admin#frag", "title": "Login"}],
        "fofa",
    )

    web = next(item for item in db.added if isinstance(item, collect.WebEndpoint))
    observation = next(item for item in db.added if isinstance(item, collect.SourceObservation))
    admin_hash = collect.build_url_hash("https://example.com/admin")

    assert web.normalized_url == "https://example.com/login"
    assert web.normalized_url_hash == collect.build_url_hash("https://example.com/login")
    assert web.normalized_url_hash != admin_hash
    assert web.source_meta["entry_url"] == "https://example.com:443/"
    assert web.source_meta["entry_url_hash"] == collect.build_url_hash("https://example.com:443/")
    assert web.source_meta["entry_url_hash"] != web.normalized_url_hash
    assert observation.raw_payload["normalized_url"] == "https://example.com/login"
    assert observation.raw_payload["entry_url"] == "https://example.com:443/"


def test_save_assets_duplicate_only_backfills_empty_source_meta_fields():
    existing = WebEndpoint(
        normalized_url="https://example.com",
        normalized_url_hash=collect.build_url_hash("https://example.com"),
        title="Keep me",
        status_code=200,
        verified=True,
        screenshot_status="success",
        source_meta={
            "source": "fofa",
            "host": "example.com",
            "import_job_id": "old-job",
            "post_process_job_id": "historic-job",
            "post_process_job_ids": ["historic-job"],
        },
        first_seen_at=datetime(2026, 4, 18, 8, 0, 0),
        last_seen_at=datetime(2026, 4, 18, 8, 0, 0),
    )
    db = DuplicateDb(existing)
    job = SimpleNamespace(success_count=0, duplicate_count=0, failed_count=0, dedup_strategy="overwrite", id="job-1")

    collect.save_assets(
        db,
        job,
        [{"url": "https://example.com/login", "title": "Replace me"}],
        "hunter",
    )

    assert job.duplicate_count == 1
    assert existing.source_meta["source"] == "fofa"
    assert existing.source_meta["host"] == "example.com"
    assert existing.source_meta["import_job_id"] == "old-job"
    assert existing.source_meta["post_process_job_id"] == "historic-job"
    assert existing.source_meta["post_process_job_ids"] == ["historic-job"]
    assert existing.source_meta.get("verify_job_ids") is None
    assert existing.source_meta.get("screenshot_job_ids") is None
    assert existing.last_seen_at > datetime(2026, 4, 18, 8, 0, 0)
    assert existing.source_meta["source_record_id"] == "hunter:url:https://example.com/login"
    assert existing.verified is True
    assert existing.screenshot_status == "success"
    observations = [item for item in db.added if isinstance(item, collect.SourceObservation)]
    assert len(observations) == 1


def test_save_assets_keeps_observation_when_url_cannot_be_built():
    db = ObservationOnlyDb()
    job = SimpleNamespace(success_count=0, duplicate_count=0, failed_count=0, dedup_strategy="overwrite", id="job-2")

    collect.save_assets(
        db,
        job,
        [{"title": "No URL", "ip": "1.1.1.1", "port": 22, "protocol": "tcp", "raw_data": {"record": 1}}],
        "hunter",
    )

    observations = [item for item in db.added if isinstance(item, collect.SourceObservation)]
    web_assets = [item for item in db.added if isinstance(item, collect.WebEndpoint)]

    assert job.success_count == 1
    assert job.duplicate_count == 0
    assert job.failed_count == 0
    assert web_assets == []
    assert len(observations) == 1
    assert observations[0].raw_payload["observation_only"] is True


def test_collect_job_asset_ids_recovers_legacy_fallback_fields():
    asset = SimpleNamespace(
        id="asset-legacy",
        normalized_url="https://legacy.example.com/",
        domain="legacy.example.com",
        source_meta={"domain": "legacy.example.com", "host": "legacy.example.com", "port": 443},
    )
    observation = SimpleNamespace(
        collect_job_id="job-legacy",
        source_record_id=None,
        raw_payload={
            "fallback_url": "https://legacy.example.com",
            "resolved_domain": "legacy.example.com",
            "resolved_port": 443,
        },
    )

    class ObservationQuery:
        def __init__(self, items):
            self.items = items

        def filter(self, *_args, **_kwargs):
            return self

        def order_by(self, *_args, **_kwargs):
            return self

        def all(self):
            return list(self.items)

    class AssetQuery:
        def __init__(self, items):
            self.items = items

        def filter(self, *_args, **_kwargs):
            return self

        def all(self):
            return list(self.items)

    class Db:
        def query(self, model):
            if model is collect.SourceObservation:
                return ObservationQuery([observation])
            assert model is collect.WebEndpoint
            return AssetQuery([asset])

    assert collect._collect_job_asset_ids(Db(), "job-legacy") == ["asset-legacy"]


def test_iter_job_scoped_assets_includes_duplicate_assets_for_mixed_job(monkeypatch):
    new_asset = WebEndpoint(id="new-1", normalized_url="https://new.example.com")
    duplicate_asset = WebEndpoint(id="dup-1", normalized_url="https://dup.example.com")
    db = IterAssetsDb([new_asset, duplicate_asset])

    monkeypatch.setattr(collect, "_build_job_scoped_asset_query", lambda _db, _job_id: IterAssetsQuery([new_asset]))
    monkeypatch.setattr(collect, "_collect_job_asset_ids", lambda _db, _job_id: ["dup-1", "new-1"])

    assets = collect._iter_job_scoped_assets(db, "job-mixed")

    assert [asset.id for asset in assets] == ["new-1", "dup-1"]


def test_iter_job_scoped_assets_includes_duplicate_assets_for_pure_duplicate_job(monkeypatch):
    duplicate_asset = WebEndpoint(id="dup-1", normalized_url="https://dup.example.com")
    db = IterAssetsDb([duplicate_asset])

    monkeypatch.setattr(collect, "_build_job_scoped_asset_query", lambda _db, _job_id: IterAssetsQuery([]))
    monkeypatch.setattr(collect, "_collect_job_asset_ids", lambda _db, _job_id: ["dup-1"])

    assets = collect._iter_job_scoped_assets(db, "job-dup-only")

    assert [asset.id for asset in assets] == ["dup-1"]


def test_build_job_scoped_asset_query_uses_current_job_association_list(monkeypatch):
    captured_criteria = []

    class Query:
        def outerjoin(self, *_args, **_kwargs):
            return self

        def filter(self, *criteria):
            captured_criteria.extend(criteria)
            return self

    class Db:
        def query(self, model):
            assert model is collect.WebEndpoint
            return Query()

    collect._build_job_scoped_asset_query(Db(), "job-list")

    compiled = " ".join(str(item) for item in captured_criteria)
    assert "@>" in compiled
