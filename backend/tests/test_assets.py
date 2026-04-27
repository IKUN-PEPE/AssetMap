from pathlib import Path
from datetime import datetime, timezone
from types import SimpleNamespace
import asyncio
from urllib.parse import quote

from app.api import assets as assets_api
from app.api.assets import SCREENSHOT_DIR, serialize_asset
from app.models.asset import WebEndpoint
from app.models.support import Screenshot


def test_serialize_asset_returns_static_url_for_nested_screenshot_file(tmp_path: Path):
    screenshot_root = SCREENSHOT_DIR
    nested_dir = screenshot_root / "nested"
    nested_dir.mkdir(parents=True, exist_ok=True)
    screenshot_file = nested_dir / "preview.png"
    screenshot_file.write_bytes(b"fake-image")

    asset = WebEndpoint(
        id="asset-1",
        normalized_url="https://example.com",
        screenshot_status="success",
        label_status="none",
    )
    asset.screenshots = [
        Screenshot(
            file_name="preview.png",
            object_path=str(screenshot_file),
            status="success",
        )
    ]

    data = serialize_asset(asset)

    assert data["screenshot_url"] == "/static/screenshots/nested/preview.png"


def test_serialize_asset_uses_latest_existing_screenshot_when_newer_record_is_missing(tmp_path: Path):
    screenshot_root = SCREENSHOT_DIR
    existing_file = screenshot_root / "existing-preview.png"
    existing_file.write_bytes(b"fake-image")
    missing_file = screenshot_root / "missing-preview.png"

    asset = WebEndpoint(
        id="asset-2",
        normalized_url="https://example.com",
        screenshot_status="success",
        label_status="none",
    )
    asset.screenshots = [
        Screenshot(
            file_name="existing-preview.png",
            object_path=str(existing_file),
            status="success",
            captured_at=datetime(2026, 4, 13, 0, 0, 0),
        ),
        Screenshot(
            file_name="missing-preview.png",
            object_path=str(missing_file),
            status="success",
            captured_at=datetime(2026, 4, 14, 0, 0, 0),
        ),
    ]

    data = serialize_asset(asset)

    assert data["screenshot_url"] == "/static/screenshots/existing-preview.png"


def test_serialize_asset_falls_back_to_disk_file_matching_asset_id_prefix(tmp_path: Path):
    screenshot_root = SCREENSHOT_DIR
    asset = WebEndpoint(
        id="asset-4-very-long-uuid",
        normalized_url="https://58.251.18.58/",
        title="深圳地铁安全管理平台",
        screenshot_status="success",
        label_status="none",
    )
    asset_id_prefix = asset.id[:20]
    file_name = f"{asset_id_prefix}_深圳地铁安全管理平台_https___58.251.18.58_.png"
    disk_file = screenshot_root / file_name
    disk_file.write_bytes(b"fake-image")
    asset.screenshots = [
        Screenshot(
            file_name="broken.png",
            object_path=str(screenshot_root / "broken.png"),
            status="success",
            captured_at=datetime(2026, 4, 14, 0, 0, 0),
        )
    ]

    data = serialize_asset(asset)

    assert data["screenshot_url"] == f"/static/screenshots/{quote(file_name, safe='/')}"


def test_serialize_asset_url_encodes_spaces_in_screenshot_filename(tmp_path: Path):
    screenshot_root = SCREENSHOT_DIR
    screenshot_file = screenshot_root / "asset-5_404 Not Found_https___example.com.png"
    screenshot_file.write_bytes(b"fake-image")

    asset = WebEndpoint(
        id="asset-5",
        normalized_url="https://example.com",
        screenshot_status="success",
        label_status="none",
    )
    asset.screenshots = [
        Screenshot(
            file_name=screenshot_file.name,
            object_path=str(screenshot_file),
            status="success",
            captured_at=datetime(2026, 4, 14, 0, 0, 0),
        )
    ]

    data = serialize_asset(asset)

    assert data["screenshot_url"] == "/static/screenshots/asset-5_404%20Not%20Found_https___example.com.png"


class FilterableListQuery:
    def __init__(self, items):
        self.items = items
        self.criteria = []

    def options(self, *_args, **_kwargs):
        return self

    def filter(self, *criteria):
        self.criteria.extend(criteria)
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def all(self):
        result = list(self.items)
        for criterion in self.criteria:
            result = [item for item in result if _matches(item, criterion)]
        return result


class FakeDb:
    def __init__(self, items):
        self.items = items

    def query(self, model):
        assert model is WebEndpoint
        return FilterableListQuery(self.items)


def _matches(item, criterion):
    left = getattr(criterion, "left", None)
    right = getattr(criterion, "right", None)
    key = getattr(left, "key", None)
    operator = getattr(getattr(criterion, "operator", None), "__name__", None)
    value = getattr(right, "value", None)
    candidate = getattr(item, key, None)

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



def test_get_month_bounds_utc8_uses_china_calendar_month():
    assert assets_api.get_month_bounds_utc8.__module__ == "app.api.assets"
    start, end = assets_api.get_month_bounds_utc8(datetime(2026, 4, 22, 10, 0, tzinfo=timezone.utc))

    assert start == datetime(2026, 3, 31, 16, 0)
    assert end == datetime(2026, 4, 30, 16, 0)


def test_expand_source_filter_values_groups_csv_and_api_sources():
    assert assets_api.expand_source_filter_values("fofa") == ("fofa", "fofa_csv")
    assert assets_api.expand_source_filter_values("hunter") == ("hunter", "hunter_csv")
    assert assets_api.expand_source_filter_values("zoomeye") == ("zoomeye", "zoomeye_csv")
    assert assets_api.expand_source_filter_values("quake") == ("quake", "quake_csv")
    assert assets_api.expand_source_filter_values("sample") == ("sample",)


def test_list_assets_filters_month_new_assets(monkeypatch):
    month_start = datetime(2026, 3, 31, 16, 0, 0)
    month_end = datetime(2026, 4, 30, 16, 0, 0)
    items = [
        SimpleNamespace(
            id="old",
            normalized_url="https://old.example.com",
            title="old",
            status_code=None,
            screenshot_status="none",
            label_status="none",
            verified=False,
            source_meta={},
            first_seen_at=datetime(2026, 3, 20, 10, 0, 0),
            last_seen_at=datetime(2026, 3, 20, 10, 0, 0),
            screenshots=[],
        ),
        SimpleNamespace(
            id="month",
            normalized_url="https://month.example.com",
            title="month",
            status_code=None,
            screenshot_status="none",
            label_status="none",
            verified=False,
            source_meta={},
            first_seen_at=datetime(2026, 4, 12, 10, 0, 0),
            last_seen_at=datetime(2026, 4, 12, 10, 0, 0),
            screenshots=[],
        ),
        SimpleNamespace(
            id="future",
            normalized_url="https://future.example.com",
            title="future",
            status_code=None,
            screenshot_status="none",
            label_status="none",
            verified=False,
            source_meta={},
            first_seen_at=datetime(2026, 4, 30, 16, 0, 0),
            last_seen_at=datetime(2026, 4, 30, 16, 0, 0),
            screenshots=[],
        ),
    ]

    monkeypatch.setattr(assets_api, "get_month_bounds_utc8", lambda: (month_start, month_end))

    result = assets_api.list_assets(db=FakeDb(items), month_new=True)

    assert [item["id"] for item in result] == ["month"]


def test_capture_asset_screenshot_works_when_called_from_async_context(tmp_path: Path, monkeypatch):
    recorded = {}

    async def fake_run_screenshot_job(**kwargs):
        recorded.update(kwargs)
        return {"summary_text": "ok"}

    monkeypatch.setattr(assets_api, "run_screenshot_job", fake_run_screenshot_job)
    monkeypatch.setattr(assets_api.settings, "screenshot_output_dir", str(tmp_path))
    monkeypatch.setattr(assets_api.settings, "result_output_dir", str(tmp_path))

    asset = WebEndpoint(
        id="asset-3",
        normalized_url="https://example.com",
        title="Example",
        domain="example.com",
        screenshot_status="none",
        label_status="none",
    )

    async def runner():
        return await assets_api.capture_asset_screenshot_async(asset)

    screenshot_path = asyncio.run(runner())

    assert screenshot_path.endswith("asset-3_Example_https___example.com.png")
    assert recorded["skip_existing"] is False
