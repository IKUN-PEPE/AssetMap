import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)


class BaseCollector(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    async def test_connection(self, config: Dict[str, Any]) -> bool:
        pass

    @abstractmethod
    async def run(self, query: str, options: Dict[str, Any], config: Dict[str, Any]) -> List[Dict[str, Any]]:
        pass

    def require_config(self, config: Dict[str, Any], key: str, label: str) -> str:
        value = str(config.get(key, "") or "").strip()
        if not value:
            raise ValueError(f"{label} 未配置")
        return value

    def get_int_option(
        self,
        options: Dict[str, Any],
        config: Dict[str, Any],
        option_key: str,
        config_key: str,
        default: int,
    ) -> int:
        raw = options.get(option_key, config.get(config_key, default))
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            return default

    def get_timeout(self, options: Dict[str, Any], default: float = 30.0) -> float:
        raw = options.get("timeout", default)
        try:
            return float(raw)
        except (TypeError, ValueError):
            return default

    def get_job_logger(self, options: Dict[str, Any]):
        candidate = options.get("_job_logger") if isinstance(options, dict) else None
        if candidate and hasattr(candidate, "info") and hasattr(candidate, "warning"):
            return candidate
        return logger

    def log_info(self, options: Dict[str, Any], message: str, *args: Any) -> None:
        self.get_job_logger(options).info(f"[{self.name}] {message}", *args)

    def log_warning(self, options: Dict[str, Any], message: str, *args: Any) -> None:
        self.get_job_logger(options).warning(f"[{self.name}] {message}", *args)

    def log_exception(self, options: Dict[str, Any], message: str, *args: Any) -> None:
        self.get_job_logger(options).exception(f"[{self.name}] {message}", *args)

    @staticmethod
    def build_url(url: Any = None, *, host: Any = None, ip: Any = None, port: Any = None, protocol: Any = None) -> str | None:
        value = str(url or "").strip()
        if value:
            if value.startswith(("http://", "https://")):
                return value
            parsed = urlsplit(f"https://{value}")
            if parsed.netloc:
                return f"https://{parsed.netloc}{parsed.path or '/'}"

        target = str(host or ip or "").strip()
        if not target:
            return None

        scheme = str(protocol or "https").strip().lower() or "https"
        try:
            port_num = int(port) if port not in (None, "") else None
        except (TypeError, ValueError):
            port_num = None

        if port_num and not ((scheme == "http" and port_num == 80) or (scheme == "https" and port_num == 443)):
            return f"{scheme}://{target}:{port_num}"
        return f"{scheme}://{target}"

    def normalize(self, raw_item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "source": self.name,
            "ip": raw_item.get("ip"),
            "port": raw_item.get("port"),
            "protocol": raw_item.get("protocol"),
            "host": raw_item.get("host"),
            "domain": raw_item.get("domain"),
            "title": raw_item.get("title"),
            "server": raw_item.get("server"),
            "country": raw_item.get("country"),
            "city": raw_item.get("city"),
            "company": raw_item.get("company"),
            "url": raw_item.get("url") or self.build_url(
                host=raw_item.get("host") or raw_item.get("domain"),
                ip=raw_item.get("ip"),
                port=raw_item.get("port"),
                protocol=raw_item.get("protocol"),
            ),
            "raw_data": raw_item,
            "collected_at": datetime.utcnow().isoformat(),
        }
