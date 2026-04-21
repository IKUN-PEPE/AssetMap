from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ScreenshotBatchRequest(BaseModel):
    asset_ids: list[str]
    skip_existing: bool = True
    priority: str = "normal"


class LabelBatchRequest(BaseModel):
    asset_ids: list[str]
    label_type: str
    reason: str | None = None
    created_by: str = "system"


class SelectionCreateRequest(BaseModel):
    selection_name: str
    selection_type: str
    filter_snapshot: dict | None = None
    asset_ids: list[str] = Field(default_factory=list)
    created_by: str = "system"


class ReportCreateRequest(BaseModel):
    report_name: str
    scope_type: str
    selection_id: str | None = None
    asset_ids: list[str] = Field(default_factory=list)
    report_formats: list[str] = Field(default_factory=lambda: ["html"])
    exclude_false_positive: bool = True
    exclude_confirmed: bool = False
    created_by: str = "system"


class ReportRead(BaseModel):
    id: str
    report_name: str
    status: str
    created_at: datetime | None = None
    finished_at: datetime | None = None
    total_assets: int | None = None
    excluded_assets: int | None = None
    error_message: str | None = None

    model_config = ConfigDict(from_attributes=True)
