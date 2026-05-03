from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExposureSearchTaskCreate(BaseModel):
    name: str
    org_keywords: list[str] = Field(default_factory=list)
    title_keywords: list[str] = Field(default_factory=list)
    url_keywords: list[str] = Field(default_factory=list)
    file_types: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    max_results: int = 100
    max_pages: int = 2
    only_documents: bool = False
    only_webpages: bool = False
    use_playwright: bool = True
    auto_run: bool = True


class ExposureSearchTaskUpdate(BaseModel):
    name: str | None = None
    status: str | None = None


class ExposureSearchResultSchema(BaseModel):
    id: str
    task_id: str
    source: str
    query: str
    title: str
    url: str
    snippet: str | None = None
    file_type: str | None = None
    risk_tags: list[str] = []
    matched_keywords: list[str] = []
    status: str
    imported_asset_id: str | None = None
    discovered_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExposureSearchTaskSchema(BaseModel):
    id: str
    name: str
    org_keywords: list[str]
    title_keywords: list[str]
    url_keywords: list[str]
    file_types: list[str]
    sources: list[str]
    query_plan: list[dict] | None = None
    status: str
    total_results: int
    valid_count: int
    ignored_count: int
    imported_count: int
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class BatchUpdateExposureResults(BaseModel):
    ids: list[str]
    status: str


class ConfirmImportExposureResults(BaseModel):
    ids: list[str]
    import_all_valid: bool = False
