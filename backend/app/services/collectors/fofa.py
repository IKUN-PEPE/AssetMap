import base64
import logging
from typing import Any, Dict, List

import httpx

from .base import BaseCollector

logger = logging.getLogger(__name__)

SEARCH_PATH = "/api/v1/search/all"
INFO_PATH = "/api/v1/info/my"


class FOFACollector(BaseCollector):
    @property
    def name(self) -> str:
        return "fofa"

    @staticmethod
    def _get_base_url(config: Dict[str, Any]) -> str:
        return str(config.get("fofa_base_url") or "https://fofa.info").rstrip("/")

    @staticmethod
    def _encode_query(query: str) -> str:
        return base64.b64encode(query.encode("utf-8")).decode("utf-8")

    @staticmethod
    def _raise_if_fofa_api_error(resp: httpx.Response, data: dict) -> None:
        errmsg = ""
        if isinstance(data, dict):
            errmsg = str(data.get("errmsg") or "").strip()

        if resp.status_code == 401:
            raise RuntimeError(errmsg or "FOFA 认证失败，请检查 email 和 key 是否正确")
        if resp.status_code == 403:
            raise RuntimeError(errmsg or "FOFA 权限不足，请检查账户权限")
        if resp.status_code == 429:
            raise RuntimeError(errmsg or "FOFA 请求频率过高，请稍后重试")
        if resp.status_code >= 500:
            raise RuntimeError(errmsg or f"FOFA 服务异常：HTTP {resp.status_code}")
        if resp.status_code >= 400:
            raise RuntimeError(errmsg or f"FOFA 查询失败：HTTP {resp.status_code}")

        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError(errmsg or "FOFA 查询失败")

    async def test_connection(self, config: Dict[str, Any]) -> bool:
        email = self.require_config(config, "fofa_email", "FOFA email")
        key = self.require_config(config, "fofa_key", "FOFA API Key")
        base_url = self._get_base_url(config)

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{base_url}{INFO_PATH}",
                params={
                    "email": email,
                    "key": key,
                },
            )

            try:
                data = resp.json() or {}
            except Exception:
                data = {}

            self._raise_if_fofa_api_error(resp, data)
            return True

    async def run(self, query: str, options: Dict[str, Any], config: Dict[str, Any]) -> List[Dict[str, Any]]:
        email = self.require_config(config, "fofa_email", "FOFA email")
        key = self.require_config(config, "fofa_key", "FOFA API Key")
        base_url = self._get_base_url(config)

        page_size = self.get_int_option(options, config, "page_size", "fofa_page_size", 10)
        max_pages = self.get_int_option(options, config, "max_pages", "fofa_max_pages", 10)
        limit = self.get_int_option(options, config, "limit", "fofa_limit", page_size * max_pages)

        qbase64 = self._encode_query(query)
        results: List[Dict[str, Any]] = []

        self.log_info(
            options,
            "query=%s page_size=%s max_pages=%s limit=%s",
            query,
            page_size,
            max_pages,
            limit,
        )

        async with httpx.AsyncClient(timeout=self.get_timeout(options)) as client:
            for page in range(1, max_pages + 1):
                self.log_info(options, "request page=%s", page)

                resp = await client.get(
                    f"{base_url}{SEARCH_PATH}",
                    params={
                        "email": email,
                        "key": key,
                        "qbase64": qbase64,
                        "page": page,
                        "size": page_size,
                        "full": "true",
                        "r_type": "json",
                        "fields": "ip,port,protocol,host,domain,title,server,country,city,as_organization,link",
                    },
                )

                try:
                    data = resp.json() or {}
                except Exception:
                    data = {}

                self._raise_if_fofa_api_error(resp, data)

                page_results = data.get("results") or []
                self.log_info(options, "response page=%s items=%s", page, len(page_results))

                if not page_results:
                    break

                for item in page_results:
                    raw = {
                        "ip": item[0] if len(item) > 0 else None,
                        "port": item[1] if len(item) > 1 else None,
                        "protocol": item[2] if len(item) > 2 else None,
                        "host": item[3] if len(item) > 3 else None,
                        "domain": item[4] if len(item) > 4 else None,
                        "title": item[5] if len(item) > 5 else None,
                        "server": item[6] if len(item) > 6 else None,
                        "country": item[7] if len(item) > 7 else None,
                        "city": item[8] if len(item) > 8 else None,
                        "company": item[9] if len(item) > 9 else None,
                        "url": item[10] if len(item) > 10 else None,
                        "raw_data": item,
                    }

                    results.append(self.normalize(raw))

                    if len(results) >= limit:
                        self.log_info(options, "limit reached collected=%s", len(results))
                        return results

        return results