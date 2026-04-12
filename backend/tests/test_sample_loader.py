from pathlib import Path

from app.services.collectors.sample_loader import load_sample_records


def test_load_sample_records_reads_json_list(tmp_path: Path):
    sample_path = tmp_path / "assets.json"
    sample_path.write_text('[{"url": "https://example.com"}]', encoding="utf-8")
    records = load_sample_records(sample_path)
    assert records == [{"url": "https://example.com"}]
