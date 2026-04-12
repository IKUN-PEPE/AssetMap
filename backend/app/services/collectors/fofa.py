from pathlib import Path

from app.services.collectors.base import BaseCollector
from app.services.collectors.sample_loader import load_sample_records


class FofaCollector(BaseCollector):
    source_name = "fofa"

    def __init__(self, sample_path: Path | None = None):
        self.sample_path = sample_path

    def search(self, query: dict) -> list[dict]:
        if self.sample_path:
            return load_sample_records(self.sample_path)
        return []
