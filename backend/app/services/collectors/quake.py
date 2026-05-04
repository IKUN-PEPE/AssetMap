from typing import Any, Dict, List
import re

import httpx

from app.services.collectors.base import BaseCollector


SEARCH_PATH = "/api/v3/search/quake_service"


def _raise_if_quake_api_error(resp: httpx.Response, data: dict) -> None:
    code = data.get("code")
    try:
        if isinstance(code, str) and code.isdigit():
            code = int(code)
    except Exception:
        pass

    message = (
        data.get("message")
        or data.get("msg")
        or data.get("error")
        or f"Quake API error: code={code}"
    )

    if resp.status_code in {401, 403}:
        raise RuntimeError(message or "Quake 认证失败，请检查 API Key 是否正确")
    if resp.status_code == 429:
        raise RuntimeError(message or "Quake 请求频率过高，请稍后重试")
    if resp.status_code >= 500:
        raise RuntimeError(message or f"Quake 服务异常：HTTP {resp.status_code}")
    if resp.status_code >= 400:
        raise RuntimeError(message or f"Quake 查询失败：HTTP {resp.status_code}")

    if code in (None, 0, 200):
        return

    raise RuntimeError(str(message))


class QuakeCollector(BaseCollector):
    @property
    def name(self) -> str:
        return "quake"

    @staticmethod
    def _get_base_url(config: Dict[str, Any]) -> str:
        return str(config.get("quake_base_url") or "https://quake.360.net").rstrip("/")

    @staticmethod
    def _build_headers(token: str) -> Dict[str, str]:
        return {
            "X-QuakeToken": token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
        }

    @staticmethod
    def _extract_items(data: dict) -> list[dict]:
        payload = data.get("data")

        if isinstance(payload, list):
            return payload

        if isinstance(payload, dict):
            if isinstance(payload.get("data"), list):
                return payload.get("data") or []
            if isinstance(payload.get("items"), list):
                return payload.get("items") or []

        if isinstance(data.get("items"), list):
            return data.get("items") or []

        return []

    @staticmethod
    def _clean_text(value: Any) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        if text in {"暂无权限", "null", "None"}:
            return ""
        return text

    @classmethod
    def _extract_title_from_html(cls, html: str) -> str:
        html = cls._clean_text(html)
        if not html:
            return ""

        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if not match:
            return ""

        title = re.sub(r"\s+", " ", match.group(1)).strip()
        return cls._clean_text(title)

    @classmethod
    def _pick_title(cls, item: dict, service_payload: dict, http_payload: dict) -> str:
        # 1. 顶层 title（如果有）
        title = cls._clean_text(item.get("title"))
        if title:
            return title

        # 2. 正确位置：service.http.title
        title = cls._clean_text(http_payload.get("title"))
        if title:
            return title

        # 3. 某些数据 title 为空，但 response/body 里其实有 <title>
        title = cls._extract_title_from_html(http_payload.get("body") or "")
        if title:
            return title

        title = cls._extract_title_from_html(service_payload.get("response") or "")
        if title:
            return title

        return ""

    async def _request_search(
        self,
        client: httpx.AsyncClient,
        *,
        base_url: str,
        token: str,
        query: str,
        start: int,
        size: int,
    ) -> tuple[httpx.Response, dict]:
        resp = await client.post(
            f"{base_url}{SEARCH_PATH}",
            headers=self._build_headers(token),
            json={
                "query": query,
                "start": start,
                "size": size,
            },
        )

        try:
            data = resp.json() or {}
        except Exception:
            data = {}

        return resp, data

    async def test_connection(self, config: Dict[str, Any]) -> bool:
        token = self.require_config(config, "quake_api_key", "Quake API Key")
        base_url = self._get_base_url(config)

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp, data = await self._request_search(
                client,
                base_url=base_url,
                token=token,
                query='ip:"1.1.1.1"',
                start=0,
                size=1,
            )

            _raise_if_quake_api_error(resp, data)
            return True

    async def run(self, query: str, options: Dict[str, Any], config: Dict[str, Any]) -> List[Dict[str, Any]]:
        token = self.require_config(config, "quake_api_key", "Quake API Key")
        base_url = self._get_base_url(config)

        page_size = self.get_int_option(options, config, "page_size", "quake_page_size", 10)
        max_pages = self.get_int_option(options, config, "max_pages", "quake_max_pages", 10)
        limit = self.get_int_option(options, config, "limit", "quake_limit", page_size * max_pages)

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
                start = (page - 1) * page_size
                self.log_info(options, "request page=%s start=%s", page, start)

                resp, data = await self._request_search(
                    client,
                    base_url=base_url,
                    token=token,
                    query=query,
                    start=start,
                    size=page_size,
                )

                _raise_if_quake_api_error(resp, data)

                items = self._extract_items(data)
                self.log_info(options, "response page=%s items=%s", page, len(items))

                if not items:
                    break

                for item in items:
                    service_payload = item.get("service") if isinstance(item.get("service"), dict) else {}
                    http_payload = service_payload.get("http") if isinstance(service_payload.get("http"), dict) else {}

                    raw_port = item.get("port")
                    location = item.get("location") or {}

                    service_name = self._clean_text(service_payload.get("name"))
                    protocol = (
                        service_name
                        or self._clean_text(item.get("protocol"))
                        or ("https" if str(raw_port) == "443" else "http")
                    )

                    domain = self._clean_text(item.get("domain")) or None

                    # host 也优先从 service.http.host 取，实际数据里这个值很常见
                    host = (
                        self._clean_text(http_payload.get("host"))
                        or self._clean_text(item.get("host"))
                        or domain
                        or self._clean_text(item.get("hostname"))
                        or self._clean_text(item.get("ip"))
                    )

                    title = self._pick_title(item, service_payload, http_payload)

                    raw = {
                        "ip": item.get("ip"),
                        "port": raw_port,
                        "protocol": protocol,
                        "host": host,
                        "domain": domain,
                        "title": title,
                        "server": self._clean_text(item.get("server"))
                        or self._clean_text(http_payload.get("server"))
                        or self._clean_text(service_payload.get("product")),
                        "country": self._clean_text(item.get("country"))
                        or self._clean_text(location.get("country_cn"))
                        or self._clean_text(location.get("country")),
                        "city": self._clean_text(item.get("city"))
                        or self._clean_text(location.get("city_cn"))
                        or self._clean_text(location.get("city")),
                        "company": self._clean_text(item.get("org"))
                        or self._clean_text(item.get("organization")),
                        "url": self._clean_text(item.get("url"))
                        or self._clean_text(item.get("http_load_url"))
                        or self.build_url(
                            host=host,
                            ip=item.get("ip"),
                            port=raw_port,
                            protocol=("https" if str(raw_port) == "443" else "http"),
                        ),
                        "raw_data": item,
                    }

                    results.append(self.normalize(raw))

                    if len(results) >= limit:
                        self.log_info(options, "limit reached collected=%s", len(results))
                        return results

        return results