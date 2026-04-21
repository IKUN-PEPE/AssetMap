import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.schemas.system import ConfigTestRequest, SystemConfigRead
from app.services.collectors import get_collector
from app.services.system_service import SystemConfigService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/config")
def get_runtime_system_config():
    return {
        "sample_mode": settings.sample_mode,
        "screenshot_output_dir": settings.screenshot_output_dir,
        "result_output_dir": settings.result_output_dir,
        "database_url": settings.database_url,
    }


@router.get("/", response_model=List[SystemConfigRead])
def get_all_configs(reveal_sensitive: bool = Query(False), db: Session = Depends(get_db)):
    SystemConfigService.init_defaults(db)
    configs = SystemConfigService.get_all_configs(db)
    if not reveal_sensitive:
        for item in configs:
            if item.is_sensitive and item.config_value:
                item.config_value = "******"
    return configs


@router.put("/")
def update_configs(configs: Dict[str, Any], db: Session = Depends(get_db)):
    try:
        filtered_configs = {k: v for k, v in configs.items() if v != "******"}
        SystemConfigService.update_configs(db, filtered_configs)
        return {"message": "Configs updated successfully"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/test-connection")
async def test_platform_connection(payload: ConfigTestRequest, db: Session = Depends(get_db)):
    try:
        collector = get_collector(payload.platform)
        config_to_test = SystemConfigService.get_decrypted_configs(db, payload.platform)
        for key, value in payload.config.items():
            if value != "******":
                config_to_test[key] = value
        success = await collector.test_connection(config_to_test)
        return {"success": success, "platform": payload.platform}
    except Exception as exc:
        logger.exception("Connection test failed for %s", payload.platform)
        return {"success": False, "platform": payload.platform, "error": str(exc)}


@router.post("/init")
def init_system_configs(db: Session = Depends(get_db)):
    SystemConfigService.init_defaults(db)
    return {"message": "Default configs initialized"}
