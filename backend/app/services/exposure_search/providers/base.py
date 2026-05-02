from abc import ABC, abstractmethod
from typing import Any
from pydantic import BaseModel

class ExposureSearchItem(BaseModel):
    source: str
    query: str
    title: str
    url: str
    snippet: str | None = None
    file_type: str | None = None
    raw_payload: dict = {}

class ExposureSearchProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    async def search(self, query: str, max_results: int, max_pages: int, **kwargs) -> list[ExposureSearchItem]:
        pass
