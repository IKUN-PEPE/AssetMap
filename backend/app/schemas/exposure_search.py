from datetime import datetime
from typing import Any
from pydantic import AliasChoices, model_validator

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
    headless: bool = Field(
        default=True,
        validation_alias=AliasChoices("headless", "use_playwright"),
    )
    auto_run: bool = True

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_use_playwright(cls, data: Any):
        if not isinstance(data, dict):
            return data
        if "headless" not in data and "use_playwright" in data:
            # Legacy UI sends use_playwright to mean interactive browser mode.
            data = dict(data)
            data["headless"] = not bool(data["use_playwright"])
        return data


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
    preview_url: str | None = None
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
    max_results: int
    max_pages: int
    only_documents: bool
    only_webpages: bool
    query_plan: list[dict] | None = None
    current_query: str | None = None
    next_query: str | None = None
    completed_queries: int = 0
    total_queries: int = 0
    progress_percent: int = 0
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


class RetryExposureQueryRequest(BaseModel):
    query: str
