from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/config")
def get_config():
    return {
        "sample_mode": settings.sample_mode,
        "screenshot_output_dir": settings.screenshot_output_dir,
        "result_output_dir": settings.result_output_dir,
        "database_url": settings.database_url,
    }
