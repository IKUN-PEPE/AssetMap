import json
from pathlib import Path


def load_sample_records(sample_path: Path) -> list[dict]:
    if not sample_path.exists():
        return []
    return json.loads(sample_path.read_text(encoding="utf-8"))
