from pathlib import Path
from datetime import datetime
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
