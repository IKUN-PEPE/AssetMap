from pydantic import BaseModel, ConfigDict


class AssetRead(BaseModel):
    id: str
    normalized_url: str
    domain: str | None = None
    title: str | None = None
    status_code: int | None = None
    screenshot_status: str
    label_status: str
    source: str | None = None

    model_config = ConfigDict(from_attributes=True)
