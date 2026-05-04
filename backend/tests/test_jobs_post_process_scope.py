from types import SimpleNamespace

from app.api import jobs as jobs_api


class FilterableQuery:
    def __init__(self, items):
        self.items = list(items)
        self.criteria = []

    def filter(self, *criteria):
        self.criteria.extend(criteria)
        return self

    def all(self):
        result = list(self.items)
        for criterion in self.criteria:
            result = [item for item in result if _matches(item, criterion)]
        return result


class FakeDb:
    def __init__(self, assets):
        self.assets = assets

    def query(self, model):
        assert model is jobs_api.WebEndpoint
        return FilterableQuery(self.assets)


class ObservationQuery:
    def __init__(self, items):
        self.items = list(items)

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def all(self):
        return list(self.items)


class ResultScopeDb:
    def __init__(self, observations, assets):
        self.observations = observations
        self.assets = assets

    def query(self, model):
        if model is jobs_api.SourceObservation:
            return ObservationQuery(self.observations)
        assert model is jobs_api.WebEndpoint
        return FilterableQuery(self.assets)


def _matches(item, criterion):
    source_meta = getattr(item, "source_meta", {}) or {}
    if source_meta.get("import_job_id") == "job-b":
        return True
    if source_meta.get("post_process_job_id") == "job-b":
        return True
    if "job-b" in (source_meta.get("post_process_job_ids") or []):
        return True
    return True


def test_collect_post_process_asset_stats_includes_post_process_job_ids_assets():
    legacy_asset = SimpleNamespace(
        id="asset-1",
        verified=True,
        screenshot_status="success",
        source_meta={
            "import_job_id": "job-a",
            "post_process_job_id": "job-a",
            "post_process_job_ids": ["job-a", "job-b"],
            "verify_job_ids": ["job-b"],
            "screenshot_job_ids": ["job-b"],
        },
    )
    db = FakeDb([legacy_asset])

    stats = jobs_api._collect_post_process_asset_stats("job-b", db)

    assert stats["asset_count"] == 1
    assert stats["verify_started_count"] == 1
    assert stats["screenshot_started_count"] == 1
    assert stats["verify_success"] == 1
    assert stats["screenshot_success"] == 1


def test_collect_post_process_asset_stats_keeps_legacy_single_post_process_job_id():
    legacy_asset = SimpleNamespace(
        id="asset-2",
        verified=False,
        screenshot_status="failed",
        source_meta={
            "import_job_id": "job-a",
            "post_process_job_id": "job-b",
            "verify_error": "timeout",
            "screenshot_error": "missing",
        },
    )
    db = FakeDb([legacy_asset])

    stats = jobs_api._collect_post_process_asset_stats("job-b", db)

    assert stats["asset_count"] == 1
    assert stats["verify_started_count"] == 1
    assert stats["screenshot_started_count"] == 1
    assert stats["verify_failed"] == 1
    assert stats["screenshot_failed"] == 1


def test_collect_post_process_asset_stats_does_not_inherit_historical_state_before_current_stage_runs():
    legacy_asset = SimpleNamespace(
        id="asset-3",
        verified=True,
        screenshot_status="success",
        source_meta={
            "import_job_id": "job-a",
            "post_process_job_id": "job-a",
            "post_process_job_ids": ["job-a"],
        },
    )
    duplicate_asset = SimpleNamespace(
        id="asset-4",
        verified=True,
        screenshot_status="success",
        source_meta={
            "import_job_id": "job-a",
            "post_process_job_id": "job-a",
            "post_process_job_ids": ["job-a", "job-b"],
        },
    )
    db = FakeDb([legacy_asset, duplicate_asset])

    stats = jobs_api._collect_post_process_asset_stats("job-b", db)

    assert stats["verify_started_count"] == 0
    assert stats["screenshot_started_count"] == 0
    assert stats["verify_success"] == 0
    assert stats["screenshot_success"] == 0


def test_build_observation_asset_query_does_not_add_standalone_port_filter():
    captured_criteria = []

    class Query:
        def filter(self, *criteria):
            captured_criteria.extend(criteria)
            return self

    class Db:
        def query(self, model):
            assert model is jobs_api.WebEndpoint
            return Query()

    observation = SimpleNamespace(
        source_record_id=None,
        raw_payload={"resolved_port": 443},
    )

    jobs_api._build_observation_asset_query(Db(), [observation])

    compiled = " ".join(str(item) for item in captured_criteria)
    assert "port" not in compiled.lower()


def test_build_observation_asset_query_uses_port_when_bound_to_host_identity():
    captured_criteria = []

    class Query:
        def filter(self, *criteria):
            captured_criteria.extend(criteria)
            return self

    class Db:
        def query(self, model):
            assert model is jobs_api.WebEndpoint
            return Query()

    observation = SimpleNamespace(
        source_record_id=None,
        raw_payload={"resolved_host": "dup.example.com", "resolved_port": 443},
    )

    jobs_api._build_observation_asset_query(Db(), [observation])

    compiled = " ".join(
        str(item.compile(compile_kwargs={"literal_binds": True}))
        for item in captured_criteria
    ).lower()
    assert "443" in compiled
    assert "dup.example.com" in compiled


def test_collect_result_assets_recovers_legacy_fallback_observation_without_port_blowup():
    observation = SimpleNamespace(
        collect_job_id="job-legacy",
        created_at=None,
        source_record_id=None,
        raw_payload={
            "fallback_url": "https://legacy.example.com",
            "resolved_domain": "legacy.example.com",
            "resolved_port": 443,
        },
    )
    asset = SimpleNamespace(
        id="asset-legacy",
        normalized_url="https://legacy.example.com/",
        domain="legacy.example.com",
        source_meta={"domain": "legacy.example.com", "host": "legacy.example.com", "port": 443},
        service=None,
        host=None,
    )
    db = ResultScopeDb([observation], [asset])

    assets = jobs_api._collect_result_assets("job-legacy", db)

    assert [item.id for item in assets] == ["asset-legacy"]
