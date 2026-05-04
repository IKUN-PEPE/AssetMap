import asyncio
from types import SimpleNamespace

from app.tasks import collect


class FakeCollector:
    async def run(self, query_str, query_payload, config):
        await asyncio.sleep(0)
        return [{"url": "https://example.com", "ip": "1.1.1.1", "port": 443}]


class FakeDeleteQuery:
    def filter(self, *args, **kwargs):
        return self

    def delete(self, synchronize_session=False):
        return 0


class FakeQuery:
    def __init__(self, result):
        self.result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.result


class FakeDb:
    def __init__(self, job):
        self.job = job
        self.commit_count = 0
        self.closed = False

    def query(self, model):
        return FakeQuery(self.job)

    def commit(self):
        self.commit_count += 1

    def close(self):
        self.closed = True


class CancelledPostProcessDb(FakeDb):
    def query(self, model):
        if model is collect.CollectJob:
            return FakeQuery(self.job)
        raise AssertionError("cancelled post-process should not query assets")


class AssetQuery:
    def __init__(self, assets):
        self.assets = assets

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return list(self.assets)


class ObservationQuery:
    def __init__(self, observations):
        self.observations = observations

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return list(self.observations)


class CollectAssetIdsDb:
    def __init__(self, observations, assets):
        self.observations = observations
        self.assets = assets

    def query(self, model):
        if model is collect.SourceObservation:
            return ObservationQuery(self.observations)
        if model is collect.WebEndpoint:
            return AssetQuery(self.assets)
        raise AssertionError(f"unexpected model: {model}")


class NarrowAssetQuery(AssetQuery):
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


class NarrowCollectAssetIdsDb(CollectAssetIdsDb):
    def query(self, model):
        if model is collect.SourceObservation:
            return ObservationQuery(self.observations)
        if model is collect.WebEndpoint:
            return NarrowAssetQuery(self.assets)
        raise AssertionError(f"unexpected model: {model}")


class PostProcessDb:
    def __init__(self, job, assets):
        self.job = job
        self.assets = assets
        self.commit_count = 0
        self.closed = False
        self.added = []

    def query(self, model):
        if model is collect.CollectJob:
            return FakeQuery(self.job)
        if model is collect.WebEndpoint:
            return AssetQuery(self.assets)
        if model is collect.Screenshot:
            return FakeDeleteQuery()
        raise AssertionError(f"unexpected model: {model}")

    def commit(self):
        self.commit_count += 1

    def close(self):
        self.closed = True

    def add(self, item):
        self.added.append(item)


def test_run_collector_query_uses_fresh_event_loop():
    result = collect.run_collector_query(
        FakeCollector(),
        'title="nginx"',
        {"queries": []},
        {"token": "secret"},
    )

    assert result == [{"url": "https://example.com", "ip": "1.1.1.1", "port": 443}]


def test_run_collector_query_restores_previous_event_loop(monkeypatch):
    sentinel_loop = asyncio.new_event_loop()
    created_loop = asyncio.new_event_loop()
    assigned: list[asyncio.AbstractEventLoop | None] = []

    monkeypatch.setattr(
        collect,
        "get_current_thread_event_loop",
        lambda: sentinel_loop,
    )
    monkeypatch.setattr(collect.asyncio, 'new_event_loop', lambda: created_loop)
    monkeypatch.setattr(collect.asyncio, 'set_event_loop', lambda loop: assigned.append(loop))

    collect.run_collector_query(
        FakeCollector(),
        'title="nginx"',
        {"queries": []},
        {"token": "secret"},
    )

    assert assigned == [created_loop, sentinel_loop]
    created_loop.close()
    sentinel_loop.close()


def test_run_collector_query_clears_loop_when_no_previous_loop(monkeypatch):
    created_loop = asyncio.new_event_loop()
    assigned: list[asyncio.AbstractEventLoop | None] = []

    monkeypatch.setattr(collect, "get_current_thread_event_loop", lambda: None)
    monkeypatch.setattr(collect.asyncio, 'new_event_loop', lambda: created_loop)
    monkeypatch.setattr(collect.asyncio, 'set_event_loop', lambda loop: assigned.append(loop))

    collect.run_collector_query(
        FakeCollector(),
        'title="nginx"',
        {"queries": []},
        {"token": "secret"},
    )

    assert assigned == [created_loop, None]
    created_loop.close()


def test_run_collect_task_keeps_cancelled_status_and_skips_post_process(monkeypatch):
    job = SimpleNamespace(
        id="job-1",
        status="pending",
        started_at=None,
        finished_at=None,
        progress=0,
        error_message=None,
        success_count=0,
        failed_count=0,
        duplicate_count=0,
        total_count=0,
        sources=["fofa"],
        query_payload={"queries": [{"source": "fofa", "query": 'body="ok"'}]},
        dedup_strategy="skip",
        auto_verify=True,
    )
    db = FakeDb(job)
    launched = []

    class InlineCollector:
        async def run(self, query_str, query_payload, config):
            return [{"url": "https://example.com", "ip": "1.1.1.1", "port": 443}]

    monkeypatch.setattr(collect, "SessionLocal", lambda: db)
    monkeypatch.setattr(collect, "get_collector", lambda source: InlineCollector())
    monkeypatch.setattr(
        collect.SystemConfigService,
        "get_decrypted_configs",
        lambda db, source: {"token": "secret"},
    )
    monkeypatch.setattr(
        collect,
        "_store_pending_assets",
        lambda db, job, assets, source_name, replace_existing=False: setattr(job, "status", "cancelled") or len(assets),
    )
    monkeypatch.setattr(
        collect,
        "run_in_process",
        lambda task, *args, delay=0: launched.append((task, args, delay)),
    )

    collect.run_collect_task.call_local("job-1")

    assert job.status == "cancelled"
    assert job.finished_at is not None
    assert launched == []


def test_run_collect_task_marks_partial_success_when_any_source_fails(monkeypatch):
    job = SimpleNamespace(
        id="job-partial",
        status="pending",
        started_at=None,
        finished_at=None,
        progress=0,
        error_message=None,
        success_count=0,
        failed_count=0,
        duplicate_count=0,
        total_count=0,
        sources=["fofa", "hunter"],
        query_payload={
            "queries": [
                {"source": "fofa", "query": 'body="ok"'},
                {"source": "hunter", "query": 'body="boom"'},
            ]
        },
        dedup_strategy="skip",
        auto_verify=False,
    )
    db = FakeDb(job)

    class InlineCollector:
        def __init__(self, source: str):
            self.source = source

        async def run(self, query_str, query_payload, config):
            if self.source == "hunter":
                raise RuntimeError("upstream failed")
            return [{"url": "https://example.com", "ip": "1.1.1.1", "port": 443}]

    monkeypatch.setattr(collect, "SessionLocal", lambda: db)
    monkeypatch.setattr(collect, "get_collector", lambda source: InlineCollector(source))
    monkeypatch.setattr(
        collect.SystemConfigService,
        "get_decrypted_configs",
        lambda db, source: {"token": "secret"},
    )
    monkeypatch.setattr(
        collect,
        "_store_pending_assets",
        lambda db, job, assets, source_name, replace_existing=False: len(assets),
    )

    collect.run_collect_task.call_local("job-partial")

    assert job.status == "pending_import"
    assert job.success_count == 1
    assert job.failed_count == 1
    assert job.total_count == 2
    assert "hunter failed: upstream failed" in job.error_message


def test_run_auto_post_process_returns_immediately_for_cancelled_job(monkeypatch):
    db = CancelledPostProcessDb(SimpleNamespace(id="job-1", status="cancelled"))
    monkeypatch.setattr(collect, "SessionLocal", lambda: db)

    collect.run_auto_post_process.call_local("job-1")

    assert db.closed is True


def test_run_auto_post_process_persists_verify_and_screenshot_results(monkeypatch, tmp_path):
    job = SimpleNamespace(id="job-1", status="success")
    asset_ok = SimpleNamespace(
        id="asset-1",
        domain="example.com",
        normalized_url="https://example.com",
        title="Example",
        status_code=None,
        verified=False,
        screenshot_status="none",
        source_meta={},
    )
    asset_fail = SimpleNamespace(
        id="asset-2",
        domain="bad.example.com",
        normalized_url="https://bad.example.com",
        title="Bad",
        status_code=None,
        verified=False,
        screenshot_status="none",
        source_meta={"screenshot_error": "old"},
    )
    db = PostProcessDb(job, [asset_ok, asset_fail])

    monkeypatch.setattr(collect, "SessionLocal", lambda: db)
    monkeypatch.setattr(collect, "_collect_job_asset_ids", lambda db, job_id: ["asset-1", "asset-2"])
    monkeypatch.setattr(
        collect,
        "_verify_assets_for_post_process",
        lambda assets: {
            "asset-1": (200, None),
            "asset-2": (None, "请求超时"),
        },
    )
    monkeypatch.setattr(collect, "is_job_cancelled", lambda db, job_id: False)
    monkeypatch.setattr(
        collect,
        "run_coro_in_fresh_loop",
        lambda value: value,
    )

    screenshot_dir = tmp_path / "screens"
    result_dir = tmp_path / "results"
    screenshot_dir.mkdir()
    result_dir.mkdir()
    monkeypatch.setattr(
        "app.core.config.settings",
        SimpleNamespace(screenshot_output_dir=str(screenshot_dir), result_output_dir=str(result_dir)),
    )

    def fake_run_screenshot_job(**kwargs):
        (screenshot_dir / "asset-1.png").write_text("ok", encoding="utf-8")
        return {"summary_text": "done"}

    monkeypatch.setattr("app.services.screenshot.service.run_screenshot_job", fake_run_screenshot_job)
    monkeypatch.setattr("app.services.screenshot.service.build_output_filename", lambda asset_id, title, url: f"{asset_id}.png")

    collect.run_auto_post_process.call_local("job-1")

    assert asset_ok.status_code == 200
    assert asset_ok.verified is True
    assert asset_ok.screenshot_status == "success"
    assert asset_ok.source_meta.get("verify_error") is None
    assert asset_ok.source_meta.get("screenshot_error") is None

    assert asset_fail.status_code is None
    assert asset_fail.verified is False
    assert asset_fail.screenshot_status == "failed"
    assert asset_fail.source_meta["verify_error"] == "请求超时"
    assert asset_fail.source_meta["screenshot_error"] == "截图文件未生成"
    assert db.commit_count == 2
    assert len(db.added) == 1


def test_collect_job_asset_ids_can_match_by_observation_source_record_id():
    source_record_id = "csv_import:host-port:example.com:443"
    observation = SimpleNamespace(source_record_id=source_record_id, raw_payload={}, created_at=None)
    asset = SimpleNamespace(
        id="asset-1",
        normalized_url="https://example.com",
        domain="example.com",
        source_meta={"host": "example.com", "source_record_id": source_record_id},
        host=None,
        service=None,
    )
    db = CollectAssetIdsDb([observation], [asset])

    assert collect._collect_job_asset_ids(db, "job-1") == ["asset-1"]



def test_collect_job_asset_ids_uses_narrowed_asset_lookup_query():
    observation = SimpleNamespace(raw_payload={"normalized_url": "https://example.com"}, created_at=None)
    asset = SimpleNamespace(
        id="asset-1",
        normalized_url="https://example.com",
        domain="example.com",
        source_meta={"host": "example.com"},
        host=None,
        service=None,
    )
    db = NarrowCollectAssetIdsDb([observation], [asset])

    assert collect._collect_job_asset_ids(db, "job-1") == ["asset-1"]



def test_collect_job_asset_ids_can_resolve_assets_without_raw_payload_ids():
    observation = SimpleNamespace(
        raw_payload={
            "ip": "1.1.1.1",
            "port": 443,
            "asset_identity_key": "host-port:example.com:443",
        },
        created_at=None,
    )
    asset = SimpleNamespace(
        id="asset-1",
        normalized_url="https://example.com",
        domain=None,
        source_meta={"host": "example.com", "ip": "1.1.1.1", "port": 443, "asset_identity_key": "host-port:example.com:443"},
        host=None,
        service=None,
    )
    db = CollectAssetIdsDb([observation], [asset])

    assert collect._collect_job_asset_ids(db, "job-1") == ["asset-1"]
