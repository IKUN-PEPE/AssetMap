import base64

import pytest

from app.services.collectors.fofa import FOFACollector
from app.services.collectors.hunter import HunterCollector
from app.services.collectors.quake import QuakeCollector
from app.services.collectors.zoomeye import ZoomEyeCollector


@pytest.mark.asyncio
async def test_fofa_test_connection_requires_email_and_key():
    collector = FOFACollector()

    with pytest.raises(ValueError, match="FOFA email"):
        await collector.test_connection({})

    with pytest.raises(ValueError, match="FOFA API Key"):
        await collector.test_connection({"fofa_email": "user@example.com"})


@pytest.mark.asyncio
async def test_hunter_test_connection_requires_api_key():
    collector = HunterCollector()

    with pytest.raises(ValueError, match="Hunter API Key"):
        await collector.test_connection({})


@pytest.mark.asyncio
async def test_hunter_test_connection_uses_userinfo_endpoint(monkeypatch):
    collector = HunterCollector()
    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "code": 200,
                "message": "success",
                "data": {
                    "type": "个人账号",
                    "rest_equity_point": 1000,
                    "rest_free_point": 499,
                    "rest_export_quota": -1,
                    "day_free_point": 500,
                    "day_export_quota": -1,
                    "once_export_quota": 10000,
                    "personal_info": {
                        "username": "大牛",
                        "phone": "13700001111",
                        "is_charge": True,
                    },
                },
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, **kwargs):
            captured["url"] = url
            captured["params"] = kwargs.get("params")
            return FakeResponse()

    monkeypatch.setattr("app.services.collectors.hunter.httpx.AsyncClient", lambda *args, **kwargs: FakeClient())

    ok = await collector.test_connection({"hunter_api_key": "good"})

    assert ok is True
    assert captured["url"] == "https://hunter.qianxin.com/openApi/userInfo"
    assert captured["params"] == {"api-key": "good"}


@pytest.mark.asyncio
async def test_hunter_test_connection_raises_when_userinfo_body_code_is_not_success(monkeypatch):
    collector = HunterCollector()

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"code": 400, "message": "请求失败", "data": None}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.services.collectors.hunter.httpx.AsyncClient", lambda *args, **kwargs: FakeClient())

    with pytest.raises(RuntimeError, match="Hunter.*400.*请求失败"):
        await collector.test_connection({"hunter_api_key": "bad"})


@pytest.mark.asyncio
async def test_hunter_test_connection_raises_friendly_message_for_403(monkeypatch):
    collector = HunterCollector()

    class FakeResponse:
        status_code = 403

        def json(self):
            return {"code": 403, "message": "权限不足", "data": None}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.services.collectors.hunter.httpx.AsyncClient", lambda *args, **kwargs: FakeClient())

    with pytest.raises(RuntimeError, match="Hunter 接口返回 403"):
        await collector.test_connection({"hunter_api_key": "bad"})


@pytest.mark.asyncio
async def test_hunter_run_raises_when_body_code_is_not_success(monkeypatch):
    collector = HunterCollector()

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"code": 401, "message": "API KEY 无效"}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.services.collectors.hunter.httpx.AsyncClient", lambda *args, **kwargs: FakeClient())

    with pytest.raises(RuntimeError, match="API KEY"):
        await collector.run('ip="1.1.1.1"', {}, {"hunter_api_key": "bad"})


@pytest.mark.asyncio
async def test_hunter_run_does_not_fill_domain_with_ip(monkeypatch):
    collector = HunterCollector()

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "code": 200,
                "data": {
                    "arr": [
                        {
                            "ip": "1.1.1.1",
                            "port": 22,
                            "protocol": "ssh",
                            "domain": None,
                            "url": None,
                        }
                    ]
                },
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.services.collectors.hunter.httpx.AsyncClient", lambda *args, **kwargs: FakeClient())

    results = await collector.run('ip="1.1.1.1"', {"limit": 1}, {"hunter_api_key": "secret"})

    assert results[0]["host"] == "1.1.1.1"
    assert results[0]["domain"] is None


@pytest.mark.asyncio
async def test_hunter_run_uses_base64url_encoded_search_and_expected_params(monkeypatch):
    collector = HunterCollector()
    captured = {}
    query = 'title="北京"'
    expected = base64.urlsafe_b64encode(query.encode("utf-8")).decode("ascii")

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"code": 200, "message": "success", "data": {"arr": []}}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, **kwargs):
            captured["url"] = url
            captured["params"] = kwargs.get("params")
            return FakeResponse()

    monkeypatch.setattr("app.services.collectors.hunter.httpx.AsyncClient", lambda *args, **kwargs: FakeClient())

    results = await collector.run(query, {"page_size": 5}, {"hunter_api_key": "secret"})

    assert results == []
    assert captured["url"] == "https://hunter.qianxin.com/openApi/search"
    assert captured["params"]["api-key"] == "secret"
    assert captured["params"]["search"] == expected
    assert captured["params"]["page"] == 1
    assert captured["params"]["page_size"] == 5
    assert captured["params"]["is_web"] == 1


@pytest.mark.asyncio
async def test_hunter_run_parses_search_results_from_arr(monkeypatch):
    collector = HunterCollector()

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "code": 200,
                "message": "success",
                "data": {
                    "account_type": "个人账号",
                    "total": 1,
                    "arr": [
                        {
                            "ip": "127.0.0.1",
                            "port": 443,
                            "domain": "abc.qianxin.com",
                            "url": "https://abc.qianxin.com",
                            "web_title": "欢迎登录",
                            "protocol": "https",
                            "base_protocol": "tcp",
                            "status_code": 200,
                            "country": "中国",
                            "province": "山东省",
                            "city": "济南市",
                            "isp": "中国电信",
                            "as_org": "Chinanet",
                            "component": [{"name": "Nginx", "version": "1.20.2"}],
                            "updated_at": "2025-01-01",
                            "header_server": "nginx",
                        }
                    ],
                    "consume_quota": "消耗积分：1",
                    "rest_quota": "今日剩余积分：499",
                    "syntax_prompt": "",
                },
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.services.collectors.hunter.httpx.AsyncClient", lambda *args, **kwargs: FakeClient())

    results = await collector.run(
        'web.title="后台管理"',
        {"max_pages": 1, "limit": 1},
        {"hunter_api_key": "secret"},
    )

    assert len(results) == 1
    assert results[0]["title"] == "欢迎登录"
    assert results[0]["url"] == "https://abc.qianxin.com"
    assert results[0]["ip"] == "127.0.0.1"
    assert results[0]["port"] == 443
    assert results[0]["domain"] == "abc.qianxin.com"
    assert results[0]["status_code"] == 200
    assert results[0]["source"] == "hunter"


@pytest.mark.asyncio
async def test_fofa_test_connection_requires_email_and_key():
    collector = FOFACollector()

    with pytest.raises(ValueError, match="FOFA email"):
        await collector.test_connection({})

    with pytest.raises(ValueError, match="FOFA API Key"):
        await collector.test_connection({"fofa_email": "user@example.com"})


@pytest.mark.asyncio
async def test_zoomeye_test_connection_requires_api_key():
    collector = ZoomEyeCollector()

    with pytest.raises(ValueError, match="ZoomEye API Key"):
        await collector.test_connection({})


@pytest.mark.asyncio
async def test_zoomeye_test_connection_accepts_body_without_code_even_if_error_field_present(monkeypatch):
    collector = ZoomEyeCollector()

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"error": "Invalid API key"}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, *_args, **_kwargs):
            return FakeResponse()

        async def post(self, url, **kwargs):
            return await self.request("POST", url, **kwargs)

    monkeypatch.setattr("app.services.collectors.zoomeye.httpx.AsyncClient", lambda *args, **kwargs: FakeClient())

    ok = await collector.test_connection({"zoomeye_api_key": "bad"})
    assert ok is True


@pytest.mark.asyncio
async def test_zoomeye_test_connection_returns_login_required_without_org_fallback(monkeypatch):
    collector = ZoomEyeCollector()
    calls = []

    class AiResponse:
        status_code = 401

        def raise_for_status(self):
            return None

        def json(self):
            return {"code": "login_required", "error": "login required, missing Authorization header"}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, **kwargs):
            calls.append(url)
            return AiResponse()

        async def post(self, url, **kwargs):
            return await self.request("POST", url, **kwargs)

    monkeypatch.setattr("app.services.collectors.zoomeye.httpx.AsyncClient", lambda *args, **kwargs: FakeClient())

    with pytest.raises(RuntimeError, match="login required, missing Authorization header"):
        await collector.test_connection({"zoomeye_api_key": "good"})
    assert calls == ["https://api.zoomeye.ai/v2/userinfo"]


@pytest.mark.asyncio
async def test_zoomeye_run_returns_login_required_without_org_fallback(monkeypatch):
    collector = ZoomEyeCollector()

    class AiResponse:
        status_code = 401

        def json(self):
            return {"code": "login_required", "error": "login required, missing Authorization header"}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, **kwargs):
            return AiResponse()

        async def post(self, url, **kwargs):
            return await self.request("POST", url, **kwargs)

    monkeypatch.setattr("app.services.collectors.zoomeye.httpx.AsyncClient", lambda *args, **kwargs: FakeClient())

    with pytest.raises(RuntimeError, match="login required, missing Authorization header"):
        await collector.run('app:"nginx"', {}, {"zoomeye_api_key": "good"})


@pytest.mark.asyncio
async def test_quake_test_connection_requires_api_key():
    collector = QuakeCollector()

    with pytest.raises(ValueError, match="Quake API Key"):
        await collector.test_connection({})


@pytest.mark.asyncio
async def test_quake_test_connection_raises_when_body_code_is_not_success(monkeypatch):
    collector = QuakeCollector()

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"code": 401, "message": "Invalid token"}

        def raise_for_status(self):
            return None

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.services.collectors.quake.httpx.AsyncClient", lambda *args, **kwargs: FakeClient())

    with pytest.raises(RuntimeError, match="Invalid token"):
        await collector.test_connection({"quake_api_key": "bad"})


@pytest.mark.asyncio
async def test_zoomeye_run_does_not_fill_domain_with_ip(monkeypatch):
    collector = ZoomEyeCollector()

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "matches": [
                    {
                        "ip": "1.1.1.1",
                        "portinfo": {"port": 22, "service": "ssh"},
                        "site": {},
                    }
                ]
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, *_args, **_kwargs):
            return FakeResponse()

        async def post(self, url, **kwargs):
            return await self.request("POST", url, **kwargs)

    monkeypatch.setattr("app.services.collectors.zoomeye.httpx.AsyncClient", lambda *args, **kwargs: FakeClient())

    results = await collector.run('ip="1.1.1.1"', {"limit": 1}, {"zoomeye_api_key": "secret"})

    assert results[0]["host"] == "1.1.1.1"
    assert results[0]["domain"] == ""


@pytest.mark.asyncio
async def test_quake_run_does_not_fill_domain_with_ip(monkeypatch):
    collector = QuakeCollector()

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "code": 0,
                "data": [
                    {
                        "ip": "1.1.1.1",
                        "port": 22,
                        "service": {"name": "ssh"},
                    }
                ],
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, *_args, **_kwargs):
            return FakeResponse()

        async def post(self, url, **kwargs):
            return await self.request("POST", url, **kwargs)

    monkeypatch.setattr("app.services.collectors.quake.httpx.AsyncClient", lambda *args, **kwargs: FakeClient())

    results = await collector.run('ip="1.1.1.1"', {"limit": 1}, {"quake_api_key": "secret"})

    assert results[0]["host"] == "1.1.1.1"
    assert results[0]["domain"] is None


@pytest.mark.asyncio
async def test_fofa_run_uses_page_size_times_max_pages_as_default_limit(monkeypatch):
    collector = FOFACollector()
    seen_pages = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "error": False,
                "results": [[
                    "1.1.1.1",
                    443,
                    "https",
                    "demo.example.com",
                    "demo.example.com",
                    "Demo",
                    "nginx",
                    "CN",
                    "Beijing",
                    "Example Org",
                    "https://demo.example.com",
                ]],
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, _url, params=None, **_kwargs):
            seen_pages.append(params["page"])
            return FakeResponse()

    monkeypatch.setattr("app.services.collectors.fofa.httpx.AsyncClient", lambda *args, **kwargs: FakeClient())

    results = await collector.run(
        'app="nginx"',
        {},
        {"fofa_email": "user@example.com", "fofa_key": "secret", "fofa_page_size": 1, "fofa_max_pages": 2},
    )

    assert len(results) == 2
    assert seen_pages == [1, 2]


@pytest.mark.asyncio
async def test_hunter_run_uses_page_size_times_max_pages_as_default_limit(monkeypatch):
    collector = HunterCollector()
    seen_pages = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "code": 200,
                "data": {
                    "arr": [
                        {
                            "ip": "1.1.1.1",
                            "port": 443,
                            "protocol": "https",
                            "domain": "demo.example.com",
                            "web_title": "Demo",
                            "component": "nginx",
                            "country": "CN",
                            "city": "Beijing",
                            "company": "Example Org",
                            "url": "https://demo.example.com",
                        }
                    ]
                },
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, _url, params=None, **_kwargs):
            seen_pages.append(params["page"])
            return FakeResponse()

    monkeypatch.setattr("app.services.collectors.hunter.httpx.AsyncClient", lambda *args, **kwargs: FakeClient())

    results = await collector.run(
        'ip="1.1.1.1"',
        {},
        {"hunter_api_key": "secret", "hunter_page_size": 1, "hunter_max_pages": 2},
    )

    assert len(results) == 2
    assert seen_pages == [1, 2]


@pytest.mark.asyncio
async def test_zoomeye_run_uses_page_size_times_max_pages_as_default_limit(monkeypatch):
    collector = ZoomEyeCollector()
    seen_pages = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "matches": [
                    {
                        "ip": "1.1.1.1",
                        "portinfo": {"port": 443, "service": "https", "app": "nginx"},
                        "site": {
                            "host": "demo.example.com",
                            "domain": "demo.example.com",
                            "title": "Demo",
                            "url": "https://demo.example.com",
                            "server": "nginx",
                        },
                        "geoinfo": {"country": "CN", "city": "Beijing"},
                        "org": "Example Org",
                    }
                ]
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, _method, _url, json=None, **_kwargs):
            seen_pages.append(json["page"])
            return FakeResponse()

        async def post(self, url, **kwargs):
            return await self.request("POST", url, **kwargs)

    monkeypatch.setattr("app.services.collectors.zoomeye.httpx.AsyncClient", lambda *args, **kwargs: FakeClient())

    results = await collector.run(
        'app="nginx"',
        {},
        {"zoomeye_api_key": "secret", "zoomeye_page_size": 1, "zoomeye_max_pages": 2},
    )

    assert len(results) == 2
    assert seen_pages == [1, 2]


@pytest.mark.asyncio
async def test_quake_run_uses_page_size_times_max_pages_as_default_limit(monkeypatch):
    collector = QuakeCollector()
    seen_starts = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "code": 0,
                "data": [
                    {
                        "ip": "1.1.1.1",
                        "port": 443,
                        "service": {"name": "https", "product": "nginx"},
                        "domain": "demo.example.com",
                        "host": "demo.example.com",
                        "title": "Demo",
                        "country": "CN",
                        "city": "Beijing",
                        "org": "Example Org",
                        "url": "https://demo.example.com",
                    }
                ],
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, _url, json=None, **_kwargs):
            seen_starts.append(json["start"])
            return FakeResponse()

    monkeypatch.setattr("app.services.collectors.quake.httpx.AsyncClient", lambda *args, **kwargs: FakeClient())

    results = await collector.run(
        'app="nginx"',
        {},
        {"quake_api_key": "secret", "quake_page_size": 1, "quake_max_pages": 2},
    )

    assert len(results) == 2
    assert seen_starts == [0, 1]
