from typing import Any, Dict, List

import httpx

from app.services.collectors.base import BaseCollector


USERINFO_PATH = "/v2/userinfo"
SEARCH_PATH = "/v2/search"


def _raise_if_zoomeye_api_error(resp: httpx.Response, data: dict) -> None:
    code = data.get("code") if isinstance(data, dict) else None
    message = ""
    if isinstance(data, dict):
        message = str(
            data.get("message")
            or data.get("msg")
            or data.get("error")
            or data.get("detail")
            or ""
        ).strip()

    try:
        if isinstance(code, str) and code.isdigit():
            code = int(code)
    except Exception:
        pass

    if resp.status_code in {401, 403}:
        raise RuntimeError(message or "ZoomEye 认证失败，请检查 API Key 是否正确")
    if resp.status_code == 402:
        raise RuntimeError(message or "ZoomEye 查询额度不足、套餐权限不足，或当前账户无可用查询权限")
    if resp.status_code == 429:
        raise RuntimeError(message or "ZoomEye 请求频率过高，请稍后重试")
    if resp.status_code >= 500:
        raise RuntimeError(message or f"ZoomEye 服务异常：HTTP {resp.status_code}")
    if resp.status_code >= 400:
        raise RuntimeError(message or f"ZoomEye 查询失败：HTTP {resp.status_code}")

    if isinstance(code, str) and code.lower() in {
        "credits_insufficent",
        "credits_insufficient",
        "quota_insufficient",
    }:
        raise RuntimeError(message or "ZoomEye 查询额度不足，请稍后重试或充值账户积分")

    if isinstance(data, dict) and data.get("status") in {"error", "failed", "fail"}:
        raise RuntimeError(message or "ZoomEye API 返回失败")

    if code in (None, 0, 200, 60000):
        return

    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(message or "ZoomEye API 返回错误")

    if code is not None:
        raise RuntimeError(message or f"ZoomEye API error: code={code}")


class ZoomEyeCollector(BaseCollector):
    @property
    def name(self) -> str:
        return "zoomeye"

    @staticmethod
    def _get_base_url(config: Dict[str, Any]) -> str:
        return str(config.get("zoomeye_base_url") or "https://api.zoomeye.ai").rstrip("/")

    @staticmethod
    def _build_headers(api_key: str) -> Dict[str, str]:
        return {
            "API-KEY": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
        }

    @staticmethod
    def _clean_text(value: Any) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        if text in {"暂无权限", "null", "None"}:
            return ""
        return text

    @staticmethod
    def _pick_first(*values: Any) -> Any:
        for value in values:
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            return value
        return None

    @staticmethod
    def _extract_items(data: dict) -> list[dict]:
        if not isinstance(data, dict):
            return []

        # v2 常见返回
        for key in ("matches", "data", "items", "list", "results"):
            value = data.get(key)
            if isinstance(value, list):
                return value

        payload = data.get("data")
        if isinstance(payload, dict):
            for key in ("matches", "items", "data", "list", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    return value

        return []

    async def _post_json(
        self,
        client: httpx.AsyncClient,
        *,
        base_url: str,
        path: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
    ) -> tuple[httpx.Response, dict]:
        resp = await client.post(
            f"{base_url}{path}",
            headers=headers,
            json=payload,
        )
        try:
            data = resp.json() or {}
        except Exception:
            data = {}
        return resp, data

    async def test_connection(self, config: Dict[str, Any]) -> bool:
        api_key = self.require_config(config, "zoomeye_api_key", "ZoomEye API Key")
        base_url = self._get_base_url(config)

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp, data = await self._post_json(
                client,
                base_url=base_url,
                path=USERINFO_PATH,
                headers=self._build_headers(api_key),
                payload={},
            )
            _raise_if_zoomeye_api_error(resp, data)
            return True

    async def run(self, query: str, options: Dict[str, Any], config: Dict[str, Any]) -> List[Dict[str, Any]]:
        api_key = self.require_config(config, "zoomeye_api_key", "ZoomEye API Key")
        base_url = self._get_base_url(config)

        page_size = self.get_int_option(options, config, "page_size", "zoomeye_page_size", 20)
        max_pages = self.get_int_option(options, config, "max_pages", "zoomeye_max_pages", 10)
        limit = self.get_int_option(options, config, "limit", "zoomeye_limit", page_size * max_pages)

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

                resp, data = await self._post_json(
                    client,
                    base_url=base_url,
                    path=SEARCH_PATH,
                    headers=self._build_headers(api_key),
                    payload={
                        "query": query,
                        "page": page,
                        "pagesize": page_size,
                    },
                )

                _raise_if_zoomeye_api_error(resp, data)

                matches = self._extract_items(data)
                self.log_info(options, "response page=%s items=%s", page, len(matches))

                if not matches:
                    break

                for item in matches:
                    if not isinstance(item, dict):
                        continue

                    portinfo = item.get("portinfo") if isinstance(item.get("portinfo"), dict) else {}
                    site = item.get("site") if isinstance(item.get("site"), dict) else {}
                    geo = item.get("geoinfo") if isinstance(item.get("geoinfo"), dict) else {}
                    service_payload = item.get("service") if isinstance(item.get("service"), dict) else {}
                    http_payload = service_payload.get("http") if isinstance(service_payload.get("http"), dict) else {}

                    raw_port = self._pick_first(
                        portinfo.get("port"),
                        item.get("port"),
                    )

                    protocol = self._pick_first(
                        portinfo.get("service"),
                        portinfo.get("app"),
                        item.get("protocol"),
                        service_payload.get("name"),
                        "https" if str(raw_port) == "443" else "http",
                    )

                    domain = self._pick_first(
                        site.get("domain"),
                        item.get("domain"),
                    )

                    host = self._pick_first(
                        site.get("host"),
                        http_payload.get("host"),
                        domain,
                        item.get("host"),
                        item.get("hostname"),
                        item.get("ip"),
                    )

                    title = self._pick_first(
                        site.get("title"),
                        http_payload.get("title"),
                        item.get("title"),
                    )

                    server = self._pick_first(
                        site.get("server"),
                        http_payload.get("server"),
                        portinfo.get("app"),
                        service_payload.get("product"),
                        item.get("server"),
                    )

                    country = self._pick_first(
                        geo.get("country"),
                        geo.get("country_names"),
                        item.get("country"),
                    )

                    city = self._pick_first(
                        geo.get("city"),
                        geo.get("city_names"),
                        item.get("city"),
                    )

                    company = self._pick_first(
                        item.get("org"),
                        item.get("isp"),
                        item.get("organization"),
                    )

                    url = self._pick_first(
                        site.get("url"),
                        item.get("url"),
                        http_payload.get("url"),
                        self.build_url(
                            host=host,
                            ip=item.get("ip"),
                            port=raw_port,
                            protocol=str(protocol) if protocol else None,
                        ),
                    )

                    raw = {
                        "ip": item.get("ip"),
                        "port": raw_port,
                        "protocol": self._clean_text(protocol),
                        "host": self._clean_text(host),
                        "domain": self._clean_text(domain),
                        "title": self._clean_text(title),
                        "server": self._clean_text(server),
                        "country": self._clean_text(country),
                        "city": self._clean_text(city),
                        "company": self._clean_text(company),
                        "url": self._clean_text(url),
                        "raw_data": item,
                    }

                    results.append(self.normalize(raw))

                    if len(results) >= limit:
                        self.log_info(options, "limit reached collected=%s", len(results))
                        return results

        return results