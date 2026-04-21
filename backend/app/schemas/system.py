from datetime import datetime
from pydantic import BaseModel, ConfigDict


class SystemConfigBase(BaseModel):
    config_key: str
    config_value: str
    config_group: str
    is_sensitive: bool = False


class SystemConfigCreate(SystemConfigBase):
    pass


class SystemConfigUpdate(BaseModel):
    config_value: str


class SystemConfigRead(SystemConfigBase):
    id: str
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConfigTestRequest(BaseModel):
    platform: str
    config: dict
