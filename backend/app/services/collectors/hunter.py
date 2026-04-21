import base64
from typing import Any, Dict, List

import httpx

from app.services.collectors.base import BaseCollector


SEARCH_PATH = "/openApi/search"


def _raise_if_hunter_api_error(resp: httpx.Response, data: dict) -> None:
    code = data.get("code")
    try:
        if isinstance(code, str) and code.isdigit():
            code = int(code)
    except Exception:
        pass

    # Hunter 常见成功状态
    if code in (None, 0, 200):
        return

    message = data.get("message") or data.get("msg") or f"Hunter API error: code={code}"
    raise RuntimeError(str(message))


class HunterCollector(BaseCollector):
    @property
    def name(self) -> str:
        return "hunter"

    @staticmethod
    def _get_base_url(config: Dict[str, Any]) -> str:
        return str(config.get("hunter_base_url") or "https://hunter.qianxin.com").rstrip("/")

    @staticmethod
    def _encode_query(query: str) -> str:
        # 按你给的正确调用方式：标准 base64，不用 urlsafe_b64encode
        return base64.b64encode(query.encode("utf-8")).decode("utf-8")

    @staticmethod
    def _extract_page_results(data: dict) -> List[dict]:
        if not isinstance(data, dict):
            return []
        payload = data.get("data") or {}
        if not isinstance(payload, dict):
            return []
        arr = payload.get("arr") or []
        return arr if isinstance(arr, list) else []

    @staticmethod
    def _get_error_message(resp: httpx.Response, data: dict) -> str:
        message = ""
        if isinstance(data, dict):
            message = str(data.get("message") or data.get("msg") or "").strip()

        if resp.status_code == 401:
            return message or "Hunter 认证失败，请检查 API Key 是否正确"
        if resp.status_code == 403:
            return message or "Hunter 权限不足，请检查账户权限或接口权限"
        if resp.status_code == 429:
            return message or "Hunter 请求频率过高，请稍后重试"
        if resp.status_code >= 500:
            return message or f"Hunter 服务异常：HTTP {resp.status_code}"
        if resp.status_code >= 400:
            return message or f"Hunter 查询失败：HTTP {resp.status_code}"

        return message or "Hunter 返回异常"

    async def _request_json(
        self,
        client: httpx.AsyncClient,
        *,
        base_url: str,
        api_key: str,
        query: str,
        page: int,
        page_size: int,
    ) -> tuple[httpx.Response, dict]:
        resp = await client.get(
            f"{base_url}{SEARCH_PATH}",
            params={
                "api-key": api_key,
                "search": self._encode_query(query),
                "page": page,
                "page_size": page_size,
            },
        )

        try:
            data = resp.json() or {}
        except Exception:
            data = {}

        return resp, data

    async def test_connection(self, config: Dict[str, Any]) -> bool:
        api_key = self.require_config(config, "hunter_api_key", "Hunter API Key")
        base_url = self._get_base_url(config)

        async with httpx.AsyncClient(timeout=10.0) as client:
            # 用最小查询做连通性验证
            resp, data = await self._request_json(
                client,
                base_url=base_url,
                api_key=api_key,
                query='ip="1.1.1.1"',
                page=1,
                page_size=1,
            )

            if resp.status_code >= 400:
                raise RuntimeError(self._get_error_message(resp, data))

            _raise_if_hunter_api_error(resp, data)
            return True

    async def run(self, query: str, options: Dict[str, Any], config: Dict[str, Any]) -> List[Dict[str, Any]]:
        api_key = self.require_config(config, "hunter_api_key", "Hunter API Key")
        base_url = self._get_base_url(config)

        page_size = self.get_int_option(options, config, "page_size", "hunter_page_size", 10)
        max_pages = self.get_int_option(options, config, "max_pages", "hunter_max_pages", 10)
        limit = self.get_int_option(options, config, "limit", "hunter_limit", page_size * max_pages)

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

                resp, data = await self._request_json(
                    client,
                    base_url=base_url,
                    api_key=api_key,
                    query=query,
                    page=page,
                    page_size=page_size,
                )

                if resp.status_code >= 400:
                    raise RuntimeError(self._get_error_message(resp, data))

                _raise_if_hunter_api_error(resp, data)

                page_results = self._extract_page_results(data)
                self.log_info(options, "response page=%s items=%s", page, len(page_results))

                if not page_results:
                    break

                for item in page_results:
                    raw_port = item.get("port")

                    protocol = (
                        item.get("protocol")
                        or item.get("base_protocol")
                        or ("https" if str(raw_port) == "443" else "http")
                    )

                    domain = item.get("domain") or None
                    host = domain or item.get("ip")

                    raw = {
                        "ip": item.get("ip"),
                        "port": raw_port,
                        "protocol": protocol,
                        "host": host,
                        "domain": domain,
                        "title": item.get("web_title"),
                        "server": item.get("component") or item.get("web_server") or item.get("os"),
                        "country": item.get("country"),
                        "city": item.get("city"),
                        "company": item.get("company") or item.get("icp"),
                        "url": item.get("url")
                        or self.build_url(
                            host=host,
                            ip=item.get("ip"),
                            port=raw_port,
                            protocol=protocol,
                        ),
                        "raw_data": item,
                    }

                    results.append(self.normalize(raw))

                    if len(results) >= limit:
                        self.log_info(options, "limit reached collected=%s", len(results))
                        return results

        return results