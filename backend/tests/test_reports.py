from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.api import reports as reports_api
from app.models import Report


app = FastAPI()
app.include_router(reports_api.router, prefix="/api/v1/reports")
client = TestClient(app)


class FilterableReportQuery:
    def __init__(self, items):
        self.items = items
        self.criteria = []
        self._offset = 0
        self._limit = None

    def filter(self, *criteria):
        self.criteria.extend(criteria)
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def offset(self, value):
        self._offset = value
        return self

    def limit(self, value):
        self._limit = value
        return self

    def all(self):
        result = list(self.items)
        for criterion in self.criteria:
            result = [item for item in result if _matches(item, criterion)]
        if self._limit is None:
            return result[self._offset :]
        return result[self._offset : self._offset + self._limit]

    def first(self):
        rows = self.all()
        return rows[0] if rows else None


class FakeDb:
    def __init__(self, reports):
        self.reports = reports
        self.added = []
        self.deleted = []
        self.commits = 0

    def query(self, model):
        assert model is Report
        return FilterableReportQuery(self.reports)

    def add(self, report):
        self.added.append(report)
        self.reports.append(report)

    def delete(self, report):
        self.deleted.append(report)
        self.reports.remove(report)

    def commit(self):
        self.commits += 1

    def refresh(self, _report):
        return None


def _matches(item, criterion):
    left = getattr(criterion, "left", None)
    right = getattr(criterion, "right", None)
    key = getattr(left, "key", None)
    operator = getattr(getattr(criterion, "operator", None), "__name__", None)
    value = getattr(right, "value", None)
    candidate = getattr(item, key, None)

    if operator == "eq":
        return candidate == value
    if operator == "ge":
        return candidate >= value
    if operator == "gt":
        return candidate > value
    if operator == "le":
        return candidate <= value
    if operator == "lt":
        return candidate < value
    if operator == "ne":
        return candidate != value
    if operator == "is_not":
        return candidate is not value
    if operator == "is_":
        return candidate is value
    return True


def _override_db(fake_db):
    app.dependency_overrides[reports_api.get_db] = lambda: fake_db


def _clear_overrides():
    app.dependency_overrides.clear()


def test_create_report_persists_export_file_and_marks_completed(monkeypatch, tmp_path: Path):
    fake_db = FakeDb([])
    monkeypatch.setattr(reports_api.settings, "result_output_dir", str(tmp_path))
    _override_db(fake_db)
    report_content = "# report\ncontent"

    try:
        response = client.post(
            "/api/v1/reports",
            json={
                "report_name": "资产导出",
                "scope_type": "manual",
                "report_formats": ["md"],
                "report_content": report_content,
                "file_name": "asset-export.md",
                "asset_ids": ["asset-1", "asset-2"],
                "total_assets": 7,
                "excluded_assets": 2,
            },
        )
    finally:
        _clear_overrides()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["file_missing"] is False
    assert body["file_size"] == len(report_content.encode("utf-8"))
    assert Path(body["object_path"]).name.startswith("asset-export_")
    assert body["object_path"].endswith(".md")
    assert body["total_assets"] == 7
    assert body["excluded_assets"] == 2
    assert Path(body["object_path"]).read_text(encoding="utf-8") == report_content
    assert fake_db.commits == 2


def test_create_report_defaults_total_assets_from_asset_ids(monkeypatch, tmp_path: Path):
    fake_db = FakeDb([])
    monkeypatch.setattr(reports_api.settings, "result_output_dir", str(tmp_path))
    _override_db(fake_db)

    try:
        response = client.post(
            "/api/v1/reports",
            json={
                "report_name": "资产导出",
                "scope_type": "manual",
                "report_formats": ["csv"],
                "report_content": "id,url\n1,https://example.com",
                "file_name": "asset-export.csv",
                "asset_ids": ["asset-1", "asset-2", "asset-3"],
            },
        )
    finally:
        _clear_overrides()

    assert response.status_code == 200
    body = response.json()
    assert body["total_assets"] == 3
    assert body["excluded_assets"] == 0


def test_create_report_persists_failed_record_when_file_write_fails(monkeypatch, tmp_path: Path):
    fake_db = FakeDb([])
    monkeypatch.setattr(reports_api.settings, "result_output_dir", str(tmp_path))

    def broken_write_bytes(self, _content):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_bytes", broken_write_bytes)
    _override_db(fake_db)

    try:
        response = client.post(
            "/api/v1/reports",
            json={
                "report_name": "失败报告",
                "scope_type": "manual",
                "report_formats": ["md"],
                "report_content": "# report",
                "file_name": "failed-report.md",
            },
        )
    finally:
        _clear_overrides()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["object_path"] is None
    assert body["file_size"] is None
    assert body["download_url"] is None
    assert body["error_message"] == "disk full"
    assert fake_db.commits == 2
    assert len(fake_db.reports) == 1


def test_get_reports_marks_missing_file_and_includes_download_url(monkeypatch, tmp_path: Path):
    fake_db = FakeDb(
        [
            SimpleNamespace(
                id="report-1",
                report_name="月度资产导出",
                status="completed",
                report_type="md",
                object_path=str(tmp_path / "missing.md"),
                file_size=123,
                created_at=datetime(2026, 4, 22, 12, 0, 0),
                finished_at=datetime(2026, 4, 22, 12, 5, 0),
                total_assets=2,
                excluded_assets=0,
                error_message=None,
            )
        ]
    )
    _override_db(fake_db)

    try:
        response = client.get("/api/v1/reports/")
    finally:
        _clear_overrides()

    assert response.status_code == 200
    body = response.json()
    assert body[0]["status"] == "file_missing"
    assert body[0]["file_missing"] is True
    assert body[0]["download_url"] == "/api/v1/reports/report-1/download"


def test_download_and_delete_report_use_persisted_file(monkeypatch, tmp_path: Path):
    fake_db = FakeDb([])
    monkeypatch.setattr(reports_api.settings, "result_output_dir", str(tmp_path))
    _override_db(fake_db)
    report_content = "# keep me"

    try:
        create_response = client.post(
            "/api/v1/reports",
            json={
                "report_name": "归档报告",
                "scope_type": "manual",
                "report_formats": ["md"],
                "report_content": report_content,
                "file_name": "archived-report.md",
            },
        )
        report_id = create_response.json()["id"]
        object_path = Path(create_response.json()["object_path"])

        download_response = client.get(f"/api/v1/reports/{report_id}/download")
        delete_response = client.delete(f"/api/v1/reports/{report_id}")
    finally:
        _clear_overrides()

    assert download_response.status_code == 200
    assert download_response.content == report_content.encode("utf-8")
    assert 'filename="archived-report.md"' in download_response.headers["content-disposition"]
    assert delete_response.status_code == 204
    assert not object_path.exists()
    assert fake_db.reports == []


def test_regenerate_report_rewrites_file_and_marks_completed(monkeypatch, tmp_path: Path):
    report_path = tmp_path / "regen.md"
    report = SimpleNamespace(
        id="report-regen",
        report_name="閲嶇敓鎶ュ憡",
        report_type="md",
        scope_type="manual",
        scope_payload={"report_content": "# regenerated", "file_name": "regen.md"},
        object_path=str(report_path),
        file_size=None,
        total_assets=1,
        excluded_assets=0,
        created_at=datetime(2026, 4, 22, 12, 0, 0),
        finished_at=None,
        created_by="system",
        status="failed",
        error_message="old error",
    )
    fake_db = FakeDb([report])
    monkeypatch.setattr(reports_api.settings, "result_output_dir", str(tmp_path))
    _override_db(fake_db)

    try:
        response = client.post("/api/v1/reports/report-regen/regenerate")
    finally:
        _clear_overrides()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["file_missing"] is False
    assert Path(body["object_path"]).read_text(encoding="utf-8") == "# regenerated"


def test_regenerate_report_reuses_existing_file_when_scope_payload_lacks_content(monkeypatch, tmp_path: Path):
    report_path = tmp_path / "legacy.md"
    report_path.write_text("# legacy report", encoding="utf-8")
    report = SimpleNamespace(
        id="report-legacy-regen",
        report_name="legacy report",
        report_type="md",
        scope_type="manual",
        scope_payload={"file_name": "legacy.md"},
        object_path=str(report_path),
        file_size=None,
        total_assets=1,
        excluded_assets=0,
        created_at=datetime(2026, 4, 22, 12, 0, 0),
        finished_at=None,
        created_by="system",
        status="failed",
        error_message="old error",
    )
    fake_db = FakeDb([report])
    monkeypatch.setattr(reports_api.settings, "result_output_dir", str(tmp_path))
    _override_db(fake_db)

    try:
        response = client.post("/api/v1/reports/report-legacy-regen/regenerate")
    finally:
        _clear_overrides()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["file_missing"] is False
    assert Path(body["object_path"]).read_text(encoding="utf-8") == "# legacy report"
    assert body["error_message"] is None


def test_create_report_uses_unique_paths_for_same_file_name_hint(monkeypatch, tmp_path: Path):
    fake_db = FakeDb([])
    monkeypatch.setattr(reports_api.settings, "result_output_dir", str(tmp_path))
    _override_db(fake_db)

    try:
        first = client.post(
            "/api/v1/reports",
            json={
                "report_name": "资产导出1",
                "scope_type": "manual",
                "report_formats": ["csv"],
                "report_content": "id,url\n1,https://a.example.com",
                "file_name": "20260424_资产导出.csv",
            },
        )
        second = client.post(
            "/api/v1/reports",
            json={
                "report_name": "资产导出2",
                "scope_type": "manual",
                "report_formats": ["csv"],
                "report_content": "id,url\n2,https://b.example.com",
                "file_name": "20260424_资产导出.csv",
            },
        )
    finally:
        _clear_overrides()

    first_body = first.json()
    second_body = second.json()
    assert first.status_code == 200
    assert second.status_code == 200
    assert first_body["object_path"] != second_body["object_path"]
    assert Path(first_body["object_path"]).read_text(encoding="utf-8") != Path(second_body["object_path"]).read_text(encoding="utf-8")


def test_delete_one_report_does_not_remove_other_same_hint_file(monkeypatch, tmp_path: Path):
    fake_db = FakeDb([])
    monkeypatch.setattr(reports_api.settings, "result_output_dir", str(tmp_path))
    _override_db(fake_db)

    try:
        first = client.post(
            "/api/v1/reports",
            json={
                "report_name": "资产导出1",
                "scope_type": "manual",
                "report_formats": ["csv"],
                "report_content": "id,url\n1,https://a.example.com",
                "file_name": "20260424_资产导出.csv",
            },
        )
        second = client.post(
            "/api/v1/reports",
            json={
                "report_name": "资产导出2",
                "scope_type": "manual",
                "report_formats": ["csv"],
                "report_content": "id,url\n2,https://b.example.com",
                "file_name": "20260424_资产导出.csv",
            },
        )
        first_id = first.json()["id"]
        first_path = Path(first.json()["object_path"])
        second_id = second.json()["id"]
        second_path = Path(second.json()["object_path"])

        delete_response = client.delete(f"/api/v1/reports/{first_id}")
        download_response = client.get(f"/api/v1/reports/{second_id}/download")
    finally:
        _clear_overrides()

    assert delete_response.status_code == 204
    assert not first_path.exists()
    assert second_path.exists()
    assert download_response.status_code == 200
    assert download_response.content == b"id,url\n2,https://b.example.com"


def test_legacy_generating_status_is_mapped_to_running(tmp_path: Path):
    report = SimpleNamespace(
        id="report-legacy",
        report_name="legacy",
        status="generating",
        report_type="md",
        object_path=None,
        file_size=None,
        created_at=datetime(2026, 4, 22, 12, 0, 0),
        finished_at=None,
        total_assets=1,
        excluded_assets=0,
        error_message=None,
    )

    body = reports_api._serialize_report(report)

    assert body["status"] == "running"
    assert body["file_missing"] is False


def test_ensure_reports_schema_columns_upgrades_legacy_table(tmp_path: Path):
    db_path = tmp_path / "legacy_reports.db"
    engine = create_engine(f"sqlite:///{db_path}")
    SessionLocal = sessionmaker(bind=engine)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE reports (
                    id TEXT PRIMARY KEY,
                    report_name TEXT,
                    report_type TEXT,
                    scope_type TEXT,
                    scope_payload TEXT,
                    object_path TEXT,
                    total_assets INTEGER,
                    excluded_assets INTEGER,
                    created_by TEXT,
                    created_at TEXT,
                    finished_at TEXT,
                    status TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO reports (
                    id, report_name, report_type, scope_type, scope_payload,
                    object_path, total_assets, excluded_assets, created_by,
                    created_at, finished_at, status
                ) VALUES (
                    :report_id, 'legacy report', 'md', 'manual', '{}',
                    NULL, 0, 0, 'system', '2026-04-24 00:00:00', NULL, 'generating'
                )
                """
            ),
            {"report_id": str(uuid4())},
        )

    session = SessionLocal()
    try:
        reports_api.ensure_reports_schema_columns(session)
        columns = {item["name"] for item in inspect(engine).get_columns("reports")}
        assert "file_size" in columns
        assert "error_message" in columns

        reports = reports_api.get_reports(db=session)
        assert reports[0]["status"] == "running"

        created = reports_api.create_report(
            payload=reports_api.ReportCreateRequest(
                report_name="new report",
                scope_type="manual",
                report_formats=["md"],
                report_content="# ok",
                file_name="new-report.md",
            ),
            db=session,
        )
        assert created["status"] == "completed"

        fetched = reports_api.get_report(created["id"], db=session)
        assert fetched["id"] == created["id"]
        assert fetched["file_size"] == len("# ok".encode("utf-8"))
    finally:
        session.close()
