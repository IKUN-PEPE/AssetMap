from abc import ABC, abstractmethod


class BaseCollector(ABC):
    source_name: str = "base"

    @abstractmethod
    def search(self, query: dict) -> list[dict]:
        raise NotImplementedError

    def normalize(self, raw_record: dict) -> dict:
        return raw_record
