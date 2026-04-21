from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

from app.tasks import collect
from app.services.collectors.mapped_csv import MappedCsvParseResult


class FakeDb:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FailingQuery:
    def join(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        raise IntegrityError("insert", {}, Exception("duplicate hash"))

    def first(self):
        return None


class ExistingWebQuery:
    def __init__(self, seen_filters, existing_web):
        self.seen_filters = seen_filters
        self.existing_web = existing_web

    def join(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def filter(self, *args):
        self.seen_filters.extend(args)
        return self

    def first(self):
        return self.existing_web


class EmptyQuery:
    def join(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return None


class RecordingDb(FakeDb):
    def __init__(self):
        super().__init__()
        self.added = []
        self.flushed = 0

    def add(self, item):
        self.added.append(item)

    def flush(self):
        self.flushed += 1

    def refresh(self, _item):
        return None

    def query(self, *_args, **_kwargs):
        return EmptyQuery()


class RecordingDbNoRefresh(FakeDb):
    def __init__(self):
        super().__init__()
        self.added = []
        self.flushed = 0

    def add(self, item):
        self.added.append(item)

    def flush(self):
        self.flushed += 1

    def query(self, *_args, **_kwargs):
        return EmptyQuery()


def test_process_csv_import_job_updates_counts_and_reuses_save_assets(monkeypatch):
    job = SimpleNamespace(
        id="job-1",
        query_payload={"file_path": "assets.csv"},
        field_mapping={"url": "link", "ip": "ip", "port": "port"},
        success_count=0,
        failed_count=0,
        duplicate_count=0,
        total_count=0,
        progress=0,
    )
    db = FakeDb()
    seen: dict[str, object] = {}

    monkeypatch.setattr(
        collect,
        "parse_mapped_csv",
        lambda *args, **kwargs: MappedCsvParseResult(
            records=[
                {
                    "source": "csv_import",
                    "ip": "1.1.1.1",
                    "port": 443,
                    "protocol": "https",
                    "domain": None,
                    "url": "https://demo.example.com",
                    "title": "Portal",
                    "status_code": 200,
                    "observed_at": None,
                    "country": None,
                    "city": None,
                    "org": None,
                    "host": None,
                }
            ],
            failed_rows=1,
        ),
    )

    def fake_save_assets(fake_db, fake_job, assets, source_name):
        seen["assets"] = assets
        seen["source_name"] = source_name
        fake_job.success_count += 1

    monkeypatch.setattr(collect, "save_assets", fake_save_assets)

    collect.process_csv_import_job(db, job)

    assert seen["source_name"] == "csv_import"
    assert seen["assets"][0]["raw_data"]["status_code"] == 200
    assert job.total_count == 2
    assert job.failed_count == 1
    assert job.progress == 100




def test_process_csv_import_job_treats_auto_source_type_as_csv_import(monkeypatch):
    job = SimpleNamespace(
        id="job-auto",
        query_payload={"file_path": "assets.csv", "source_type": "auto"},
        field_mapping={"host": "host"},
        success_count=0,
        failed_count=0,
        duplicate_count=0,
        total_count=0,
        progress=0,
    )
    db = FakeDb()
    seen: dict[str, object] = {}

    monkeypatch.setattr(
        collect,
        "parse_mapped_csv",
        lambda *args, **kwargs: MappedCsvParseResult(
            records=[{"host": "demo.example.com", "raw_data": {}}],
            failed_rows=0,
        ),
    )

    def fake_save_assets(fake_db, fake_job, assets, source_name):
        seen["source_name"] = source_name
        fake_job.success_count += 1

    monkeypatch.setattr(collect, "save_assets", fake_save_assets)

    collect.process_csv_import_job(db, job)

    assert seen["source_name"] == "csv_import"


def test_process_csv_import_job_requires_file_path():
    job = SimpleNamespace(
        query_payload={},
        field_mapping={"url": "link", "ip": "ip", "port": "port"},
        success_count=0,
        failed_count=0,
        duplicate_count=0,
        total_count=0,
        progress=0,
    )

    with pytest.raises(ValueError, match="csv_import job is missing file_path"):
        collect.process_csv_import_job(FakeDb(), job)


def test_save_assets_rolls_back_session_after_integrity_error():
    job = SimpleNamespace(
        id="job-1",
        dedup_strategy="skip",
        success_count=0,
        duplicate_count=0,
        failed_count=0,
    )
    db = FakeDb()
    db.query = lambda *args, **kwargs: FailingQuery()

    collect.save_assets(
        db,
        job,
        [{"ip": "1.1.1.1", "port": 443, "url": "https://demo.example.com"}],
        "csv_import",
    )

    assert db.rollbacks == 1
    assert job.failed_count == 1




def test_save_assets_persists_observation_without_url(monkeypatch):
    job = SimpleNamespace(
        id='job-obs',
        dedup_strategy='skip',
        success_count=0,
        duplicate_count=0,
        failed_count=0,
        total_count=0,
    )
    db = RecordingDb()

    monkeypatch.setattr(collect, '_create_isolated_asset_session', lambda: None)

    collect.save_assets(
        db,
        job,
        [{'ip': '1.1.1.1', 'port': 443, 'host': 'demo.example.com', 'title': 'Portal'}],
        'csv_import',
    )

    observation = next(item for item in db.added if item.__class__ is collect.SourceObservation)
    assert observation.raw_payload['resolved_ip'] == '1.1.1.1'
    assert observation.raw_payload['resolved_host'] == 'demo.example.com'
    assert observation.raw_payload['normalized_url'] == 'https://demo.example.com/'
    assert job.success_count == 1
    assert job.failed_count == 0


def test_save_assets_does_not_fail_when_job_refresh_is_unavailable(monkeypatch):
    job = SimpleNamespace(
        id='job-no-refresh',
        dedup_strategy='skip',
        success_count=0,
        duplicate_count=0,
        failed_count=0,
        total_count=0,
    )
    db = RecordingDbNoRefresh()

    monkeypatch.setattr(collect, '_create_isolated_asset_session', lambda: None)

    collect.save_assets(
        db,
        job,
        [{'ip': '2.2.2.2', 'port': 80}],
        'csv_import',
    )

    assert job.success_count == 1
    assert job.failed_count == 0



def test_save_assets_accepts_subdomain_without_explicit_url(monkeypatch):
    job = SimpleNamespace(
        id='job-subdomain',
        dedup_strategy='skip',
        success_count=0,
        duplicate_count=0,
        failed_count=0,
        total_count=0,
    )
    db = RecordingDb()

    monkeypatch.setattr(collect, '_create_isolated_asset_session', lambda: None)

    collect.save_assets(
        db,
        job,
        [{'subdomain': 'api.example.com', 'title': 'Portal'}],
        'oneforall',
    )

    observation = next(item for item in db.added if item.__class__ is collect.SourceObservation)
    assert observation.raw_payload['resolved_host'] == 'api.example.com'
    assert observation.raw_payload['normalized_url'] == 'https://api.example.com/'
    assert job.success_count == 1
    assert job.failed_count == 0



def test_save_assets_records_source_record_id_on_web_endpoint_source_meta(monkeypatch):
    job = SimpleNamespace(
        id='job-source-record',
        dedup_strategy='skip',
        success_count=0,
        duplicate_count=0,
        failed_count=0,
        total_count=0,
    )
    db = RecordingDb()

    monkeypatch.setattr(collect, '_create_isolated_asset_session', lambda: None)

    collect.save_assets(
        db,
        job,
        [{'host': 'demo.example.com', 'port': 443, 'protocol': 'https'}],
        'csv_import',
    )

    web = next(item for item in db.added if item.__class__ is collect.WebEndpoint)
    observation = next(item for item in db.added if item.__class__ is collect.SourceObservation)
    assert web.source_meta['source_record_id'] == observation.source_record_id



def test_save_assets_keeps_non_web_ip_port_as_observation_only(monkeypatch):
    job = SimpleNamespace(
        id='job-tcp',
        dedup_strategy='skip',
        success_count=0,
        duplicate_count=0,
        failed_count=0,
        total_count=0,
    )
    db = RecordingDb()

    monkeypatch.setattr(collect, '_create_isolated_asset_session', lambda: None)

    collect.save_assets(
        db,
        job,
        [{'ip': '1.1.1.1', 'port': 22, 'protocol': 'tcp'}],
        'hunter',
    )

    observation = next(item for item in db.added if item.__class__ is collect.SourceObservation)
    assert observation.source_record_id == 'hunter:ip-port:1.1.1.1:22'
    assert observation.raw_payload['normalized_url'] is None
    assert not any(item.__class__ is collect.WebEndpoint for item in db.added)
    assert job.success_count == 1
    assert job.failed_count == 0



def test_save_assets_keeps_non_http_service_as_observation_only(monkeypatch):
    job = SimpleNamespace(
        id='job-ssh',
        dedup_strategy='skip',
        success_count=0,
        duplicate_count=0,
        failed_count=0,
        total_count=0,
    )
    db = RecordingDb()

    monkeypatch.setattr(collect, '_create_isolated_asset_session', lambda: None)

    collect.save_assets(
        db,
        job,
        [{'ip': '1.1.1.1', 'port': 22, 'protocol': 'ssh'}],
        'quake',
    )

    observation = next(item for item in db.added if item.__class__ is collect.SourceObservation)
    assert observation.source_record_id == 'quake:ip-port:1.1.1.1:22'
    assert observation.raw_payload['normalized_url'] is None
    assert not any(item.__class__ is collect.WebEndpoint for item in db.added)



def test_process_vendor_csv_import_job_routes_vendor_rows_through_csv_import(monkeypatch):

    job = SimpleNamespace(
        id='job-fofa',
        query_payload={'file_path': 'assets.csv', 'source_type': 'fofa'},
        field_mapping={},
        success_count=0,
        failed_count=0,
        duplicate_count=0,
        total_count=0,
        progress=0,
    )
    db = FakeDb()
    seen: dict[str, object] = {}

    monkeypatch.setitem(
        collect.CSV_SOURCE_PARSERS,
        'fofa',
        lambda _file_path: [{'url': 'https://example.com', 'raw_data': {}}],
    )

    def fake_save_assets(fake_db, fake_job, assets, source_name):
        seen['source_name'] = source_name
        fake_job.success_count += len(assets)

    monkeypatch.setattr(collect, 'save_assets', fake_save_assets)

    collect.process_csv_import_job(db, job)

    assert seen['source_name'] == 'csv_import'
