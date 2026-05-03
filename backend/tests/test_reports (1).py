from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

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
    assert body["object_path"].endswith("asset-export.md")
    assert body["total_assets"] == 7
    assert body["excluded_assets"] == 2
    assert Path(body["object_path"]).read_text(encoding="utf-8") == report_content
    assert fake_db.commits == 1


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
    assert delete_response.status_code == 204
    assert not object_path.exists()
    assert fake_db.reports == []
