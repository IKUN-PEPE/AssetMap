from pydantic import BaseModel, ConfigDict


class CollectJobCreate(BaseModel):
    job_name: str
    sources: list[str]
    queries: list[dict]
    time_window: dict | None = None
    file_path: str | None = None
    created_by: str = "system"
    dedup_strategy: str = "skip"
    field_mapping: dict = {}
    auto_verify: bool = False


class FofaCsvImportRequest(BaseModel):
    job_name: str
    file_path: str
    created_by: str = "system"


class CollectJobRead(BaseModel):
    id: str
    job_name: str
    status: str
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

    model_config = ConfigDict(from_attributes=True)
