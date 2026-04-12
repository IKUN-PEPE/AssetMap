from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BASE_DIR.parent


class Settings(BaseSettings):
    app_name: str = "AssetMap API"
    app_env: str = "development"
    debug: bool = True
    api_prefix: str = "/api/v1"
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/assetmap"
    )
    screenshot_output_dir: str = str(PROJECT_ROOT / "screenshots")
    result_output_dir: str = str(PROJECT_ROOT / "results")
    sample_data_path: str = str(BASE_DIR / "sample_data" / "assets.json")
    fofa_email: str | None = None
    fofa_key: str | None = None
    hunter_api_key: str | None = None
    zoomeye_api_key: str | None = None
    sample_mode: bool = True

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
