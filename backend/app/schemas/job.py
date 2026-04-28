from datetime import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CollectJobCreate(BaseModel):
    job_name: str
    sources: list[str]
    queries: list[dict]
    time_window: dict | None = None
    file_path: str | None = None
    source_type: str | None = None
    created_by: str = "system"
    dedup_strategy: str = "skip"
    field_mapping: dict[str, str] = Field(default_factory=dict)
    auto_verify: bool = False

    @model_validator(mode="after")
    def validate_csv_import_payload(self):
        if "csv_import" not in self.sources:
            return self

        if not self.file_path:
            raise ValueError("csv_import requires file_path and field_mapping for url, ip, port")

        vendor_source = (self.source_type or "").lower()
        if vendor_source in {"fofa", "hunter", "zoomeye", "quake"}:
            return self

        identity_fields = {"url", "ip", "host", "domain"}
        if not any(self.field_mapping.get(field) for field in identity_fields):
            raise ValueError("csv_import requires file_path and at least one identity mapping: url, ip, host, domain")
        return self


class FofaCsvImportRequest(BaseModel):
    job_name: str
    file_path: str
    created_by: str = "system"


class JobBatchIdsRequest(BaseModel):
    ids: list[str]


class JobConfirmImportRequest(BaseModel):
    ids: list[str] = Field(default_factory=list)
    import_all: bool = False


class JobTaskStage(BaseModel):
    state: Literal["disabled", "pending", "running", "success", "failed", "partial_failed"]
    started: bool
    finished: bool
    success: int
    failed: int
    last_error: str | None = None


class JobCollectionDetails(BaseModel):
    status: Literal["pending", "running", "success", "failed", "cancelled", "partial_success", "pending_import", "imported", "discarded"]
    progress: int
    observation_count: int
    result_asset_count: int


class JobPostProcessDetails(BaseModel):
    enabled: bool
    state: Literal["disabled", "pending", "running", "success", "failed", "partial_failed"]
    verify: JobTaskStage
    screenshot: JobTaskStage


class JobTaskDetails(BaseModel):
    collection: JobCollectionDetails
    post_process: JobPostProcessDetails


class CollectJobRead(BaseModel):
    id: str
    job_name: str
    status: Literal["pending", "running", "success", "failed", "cancelled", "partial_success", "pending_import", "imported", "discarded"]
    sources: dict | list
    query_payload: dict
    progress: int
    success_count: int
    failed_count: int
    duplicate_count: int
    total_count: int
    dedup_strategy: str
    field_mapping: dict
    auto_verify: bool
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None

    model_config = ConfigDict(from_attributes=True)


class CollectJobDetail(CollectJobRead):
    duration: float | None = None
    command_line: str | None = None
    task_details: JobTaskDetails | None = None


class JobPendingAssetRead(BaseModel):
    id: str
    source: str
    normalized_url: str | None = None
    url: str | None = None
    domain: str | None = None
    ip: str | None = None
    port: int | None = None
    title: str | None = None
    status_code: int | None = None
    protocol: str | None = None
    country: str | None = None
    city: str | None = None
    org: str | None = None
    status: Literal["pending", "imported", "discarded"]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JobPendingAssetListResponse(BaseModel):
    job_id: str
    items: list[JobPendingAssetRead]
    total: int
    skip: int
    limit: int


class JobBatchOperationItem(BaseModel):
    id: str
    ok: bool
    new_job_id: str | None = None
    error: str | None = None


class JobBatchOperationResponse(BaseModel):
    total: int
    success: int
    failed: int
    items: list[JobBatchOperationItem]


class JobConfirmImportResponse(BaseModel):
    job_id: str
    total: int
    success: int
    duplicate: int
    failed: int
    status: str


class JobDiscardImportResponse(BaseModel):
    job_id: str
    discarded: int
    status: str


class JobLogResponse(BaseModel):
    job_id: str
    log_state: Literal["not_started", "running", "finished", "log_not_found", "log_empty", "log_ready"]
    content: str
    exists: bool
    started_at: datetime | None = None
    finished_at: datetime | None = None
    task_details: JobTaskDetails


class JobResultPreviewItem(BaseModel):
    id: str
    source: str | None = None
    normalized_url: str
    url: str | None = None
    domain: str | None = None
    ip: str | None = None
    port: int | None = None
    title: str | None = None
    status_code: int | None = None
    verified: bool | None = None
    screenshot_status: str | None = None
    verify_error: str | None = None
    screenshot_error: str | None = None


class JobResultPreviewResponse(BaseModel):
    job_id: str
    items: list[JobResultPreviewItem]
    total: int
    skip: int
    limit: int
    task_details: JobTaskDetails
