import base64
from typing import Any, Dict, List

import httpx

from app.services.collectors.base import BaseCollector


USERINFO_PATH = "/openApi/userInfo"
SEARCH_PATH = "/openApi/search"


def _coerce_code(data: dict) -> int | str | None:
    code = data.get("code") if isinstance(data, dict) else None
    try:
        if isinstance(code, str) and code.isdigit():
            return int(code)
    except Exception:
        pass
    return code


def _json_message(data: dict) -> str:
    if not isinstance(data, dict):
        return ""
    return str(data.get("message") or data.get("msg") or data.get("error") or "").strip()


def _hunter_http_error_message(resp: httpx.Response, data: dict) -> str:
    message = _json_message(data)
    if resp.status_code == 403:
        return (
            "Hunter 接口返回 403，权限不足。请检查 API Key 是否正确、账号是否开通 OpenAPI 权限、"
            f"权益积分是否充足，以及是否配置了 IP 白名单。{f' Hunter 返回信息：{message}' if message else ''}"
        )
    if resp.status_code == 400:
        return (
            "Hunter 接口返回 400，请检查查询语法、base64url 编码、api-key、page/page_size 参数是否正确。"
            f"{f' Hunter 返回信息：{message}' if message else ''}"
        )
    if resp.status_code == 401:
        return message or "Hunter 认证失败，请检查 API Key 是否正确。"
    if resp.status_code == 429:
        return message or "Hunter 请求频率过高，请稍后重试。"
    if resp.status_code >= 500:
        return message or f"Hunter 服务异常：HTTP {resp.status_code}"
    if resp.status_code >= 400:
        return message or f"Hunter 查询失败：HTTP {resp.status_code}"
    return message or "Hunter 返回异常"


def _raise_if_hunter_api_error(resp: httpx.Response, data: dict) -> None:
    code = _coerce_code(data)
    if code in (None, 0, 200):
        return

    message = _json_message(data)
    if code == 403:
        raise RuntimeError(
            "Hunter 接口返回 403，权限不足。请检查 API Key 是否正确、账号是否开通 OpenAPI 权限、"
            f"权益积分是否充足，以及是否配置了 IP 白名单。{f' Hunter 返回信息：{message}' if message else ''}"
        )
    if code == 400:
        raise RuntimeError(
            "Hunter 接口返回 400，请检查查询语法、base64url 编码、api-key、page/page_size 参数是否正确。"
            f"{f' Hunter 返回信息：{message}' if message else ''}"
        )
    raise RuntimeError(str(message or f"Hunter API error: code={code}"))


class HunterCollector(BaseCollector):
    @property
    def name(self) -> str:
        return "hunter"

    @staticmethod
    def _get_base_url(config: Dict[str, Any]) -> str:
        return str(config.get("hunter_base_url") or "https://hunter.qianxin.com").rstrip("/")

    @staticmethod
    def _encode_query(query: str) -> str:
        return base64.urlsafe_b64encode(query.encode("utf-8")).decode("ascii")

    @staticmethod
    def _extract_page_results(data: dict) -> List[dict]:
        if not isinstance(data, dict):
            return []
        payload = data.get("data") or {}
        if not isinstance(payload, dict):
            return []
        arr = payload.get("arr") or []
        return arr if isinstance(arr, list) else []

    async def _request_json(
        self,
        client: httpx.AsyncClient,
        *,
        base_url: str,
        api_key: str,
        query: str,
        page: int,
        page_size: int,
        is_web: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        status_code: int | None = None,
        fields: str | None = None,
    ) -> tuple[httpx.Response, dict]:
        params: dict[str, Any] = {
            "api-key": api_key,
            "search": self._encode_query(query),
            "page": page,
            "page_size": page_size,
        }
        if is_web is not None:
            params["is_web"] = is_web
        if start_time:
            params["start_time"] = start_time
        if end_time:
            params["end_time"] = end_time
        if status_code is not None:
            params["status_code"] = status_code
        if fields:
            params["fields"] = fields

        resp = await client.get(f"{base_url}{SEARCH_PATH}", params=params)
        try:
            data = resp.json() or {}
        except Exception:
            data = {}
        return resp, data

    async def test_connection(self, config: Dict[str, Any]) -> bool:
        api_key = self.require_config(config, "hunter_api_key", "Hunter API Key")
        base_url = self._get_base_url(config)

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{base_url}{USERINFO_PATH}",
                params={"api-key": api_key},
            )
            try:
                data = resp.json() or {}
            except Exception:
                data = {}

            if resp.status_code >= 400:
                raise RuntimeError(_hunter_http_error_message(resp, data))

            code = _coerce_code(data)
            payload = data.get("data") if isinstance(data, dict) else None
            if code != 200 or not isinstance(payload, dict):
                message = _json_message(data)
                if code == 403:
                    raise RuntimeError(
                        "Hunter 接口返回 403，权限不足。请检查 API Key 是否正确、账号是否开通 OpenAPI 权限、"
                        f"权益积分是否充足，以及是否配置了 IP 白名单。{f' Hunter 返回信息：{message}' if message else ''}"
                    )
                if code == 400:
                    raise RuntimeError(
                        "Hunter 接口返回 400，请检查查询语法、base64url 编码、api-key、page/page_size 参数是否正确。"
                        f"{f' Hunter 返回信息：{message}' if message else ''}"
                    )
                raise RuntimeError(
                    f"Hunter 用户信息接口校验失败：code={code}. {f'Hunter 返回信息：{message}' if message else ''}".strip()
                )
            return True

    async def run(self, query: str, options: Dict[str, Any], config: Dict[str, Any]) -> List[Dict[str, Any]]:
        api_key = self.require_config(config, "hunter_api_key", "Hunter API Key")
        base_url = self._get_base_url(config)

        page_size = self.get_int_option(options, config, "page_size", "hunter_page_size", 10)
        max_pages = self.get_int_option(options, config, "max_pages", "hunter_max_pages", 10)
        limit = self.get_int_option(options, config, "limit", "hunter_limit", page_size * max_pages)

        raw_is_web = options.get("is_web", config.get("hunter_is_web", 1))
        try:
            is_web = int(raw_is_web) if raw_is_web not in (None, "") else None
        except (TypeError, ValueError):
            is_web = 1

        start_time = str(options.get("start_time", config.get("hunter_start_time", "")) or "").strip() or None
        end_time = str(options.get("end_time", config.get("hunter_end_time", "")) or "").strip() or None
        fields = str(options.get("fields", config.get("hunter_fields", "")) or "").strip() or None

        raw_status_code = options.get("status_code", config.get("hunter_status_code"))
        try:
            hunter_status_code = int(raw_status_code) if raw_status_code not in (None, "") else None
        except (TypeError, ValueError):
            hunter_status_code = None

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
                    is_web=is_web,
                    start_time=start_time,
                    end_time=end_time,
                    status_code=hunter_status_code,
                    fields=fields,
                )

                if resp.status_code >= 400:
                    raise RuntimeError(_hunter_http_error_message(resp, data))

                _raise_if_hunter_api_error(resp, data)

                page_results = self._extract_page_results(data)
                self.log_info(options, "response page=%s items=%s", page, len(page_results))

                if not page_results:
                    break

                for item in page_results:
                    raw_port = item.get("port")
                    protocol = item.get("protocol") or item.get("base_protocol") or ("https" if str(raw_port) == "443" else "http")
                    domain = item.get("domain") or None
                    host = domain or item.get("ip")

                    component = item.get("component")
                    if isinstance(component, list):
                        component_name = ", ".join(
                            str(comp.get("name") or "").strip()
                            for comp in component
                            if isinstance(comp, dict) and str(comp.get("name") or "").strip()
                        ) or None
                    else:
                        component_name = component

                    raw = {
                        "ip": item.get("ip"),
                        "port": raw_port,
                        "protocol": protocol,
                        "host": host,
                        "domain": domain,
                        "title": item.get("web_title"),
                        "status_code": item.get("status_code"),
                        "server": component_name or item.get("header_server") or item.get("web_server") or item.get("os"),
                        "country": item.get("country"),
                        "city": item.get("city"),
                        "company": item.get("company") or item.get("isp") or item.get("as_org") or item.get("icp"),
                        "url": item.get("url") or self.build_url(
                            host=host,
                            ip=item.get("ip"),
                            port=raw_port,
                            protocol=protocol,
                        ),
                        "raw_data": item,
                    }

                    normalized = self.normalize(raw)
                    normalized["status_code"] = item.get("status_code")
                    results.append(normalized)

                    if len(results) >= limit:
                        self.log_info(options, "limit reached collected=%s", len(results))
                        return results

        return results
