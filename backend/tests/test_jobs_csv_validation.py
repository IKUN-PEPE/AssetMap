import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.job import CollectJobCreate
from app.services.collectors.preview import detect_csv_source, get_csv_preview


def test_collect_job_create_requires_file_path_and_identity_mapping_for_csv_import():
    with pytest.raises(
        ValidationError,
        match="csv_import requires file_path and at least one identity mapping: url, ip, host, domain",
    ):
        CollectJobCreate(
            job_name="csv-import",
            sources=["csv_import"],
            queries=[],
            file_path="demo.csv",
            field_mapping={"title": "title"},
        )


def test_detect_csv_source_returns_fofa_for_fofa_headers():
    assert detect_csv_source(["link", "ip", "port", "title"]) == "fofa"


def test_get_csv_preview_rejects_headerless_file():
    tmp_dir = Path("backend/tests") / f"tmp_{uuid4().hex}"
    try:
        tmp_dir.mkdir(parents=True, exist_ok=False)
        csv_path = tmp_dir / "no-header.csv"
        csv_path.write_text("https://example.com,1.1.1.1,443\n", encoding="utf-8-sig")

        with pytest.raises(ValueError, match="CSV 文件缺少表头"):
            get_csv_preview(csv_path)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
