import logging
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models import SystemConfig

logger = logging.getLogger(__name__)

DEFAULT_CONFIGS = [
    ("fofa_email", "", "fofa", False),
    ("fofa_key", "", "fofa", True),
    ("fofa_page_size", "100", "fofa", False),
    ("fofa_max_pages", "10", "fofa", False),
    ("fofa_base_url", "https://fofa.info", "fofa", False),
    ("hunter_username", "", "hunter", False),
    ("hunter_api_key", "", "hunter", True),
    ("hunter_page_size", "100", "hunter", False),
    ("hunter_max_pages", "10", "hunter", False),
    ("hunter_base_url", "https://hunter.qianxin.com", "hunter", False),
    ("zoomeye_api_key", "", "zoomeye", True),
    ("zoomeye_page_size", "20", "zoomeye", False),
    ("zoomeye_max_pages", "10", "zoomeye", False),
    ("zoomeye_base_url", "https://api.zoomeye.ai", "zoomeye", False),
    ("quake_api_key", "", "quake", True),
    ("quake_page_size", "10", "quake", False),
    ("quake_max_pages", "10", "quake", False),
    ("quake_base_url", "https://quake.360.net", "quake", False),
    ("oneforall_path", "", "oneforall", False),
    ("python_path", "python", "oneforall", False),
    ("oneforall_threads", "10", "oneforall", False),
    ("oneforall_timeout", "5", "oneforall", False),
    ("oneforall_output_dir", "./oneforall_results", "oneforall", False),
    ("data_output_dir", "./results", "system", False),
    ("screenshot_output_dir", "./screenshots", "system", False),
    ("auto_dedup", "true", "system", False),
    ("auto_import", "true", "system", False),
]


class SystemConfigService:
    @staticmethod
    def get_all_configs(db: Session) -> List[SystemConfig]:
        return db.query(SystemConfig).order_by(SystemConfig.config_group, SystemConfig.config_key).all()

    @staticmethod
    def get_config_value(db: Session, key: str, default: Any = None) -> Any:
        config = db.query(SystemConfig).filter(SystemConfig.config_key == key).first()
        return config.config_value if config else default

    @staticmethod
    def get_group_configs(db: Session, group: str) -> Dict[str, Any]:
        configs = db.query(SystemConfig).filter(SystemConfig.config_group == group).all()
        return {c.config_key: c.config_value for c in configs}

    @staticmethod
    def update_configs(db: Session, configs: Dict[str, Any]):
        for key, value in configs.items():
            config = db.query(SystemConfig).filter(SystemConfig.config_key == key).first()
            if config:
                config.config_value = str(value)
            else:
                group = key.split('_')[0] if '_' in key else 'system'
                db.add(
                    SystemConfig(
                        config_key=key,
                        config_value=str(value),
                        config_group=group,
                        is_sensitive=any(flag in key.lower() for flag in ("key", "token", "password", "secret")),
                    )
                )
        db.commit()

    @staticmethod
    def init_defaults(db: Session):
        existing_keys = {
            key
            for (key,) in db.query(SystemConfig.config_key).all()
        }
        missing_configs = [
            SystemConfig(
                config_key=key,
                config_value=value,
                config_group=group,
                is_sensitive=sensitive,
            )
            for key, value, group, sensitive in DEFAULT_CONFIGS
            if key not in existing_keys
        ]
        if missing_configs:
            db.add_all(missing_configs)
            db.commit()

    @staticmethod
    def get_decrypted_configs(db: Session, group: str) -> Dict[str, Any]:
        return SystemConfigService.get_group_configs(db, group)
