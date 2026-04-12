from pydantic import BaseModel, ConfigDict


class CollectJobCreate(BaseModel):
    job_name: str
    sources: list[str]
    queries: list[dict]
    time_window: dict | None = None
    created_by: str = "system"


class CollectJobRead(BaseModel):
    id: str
    job_name: str
    status: str
    sources: dict | list
    query_payload: dict

    model_config = ConfigDict(from_attributes=True)
