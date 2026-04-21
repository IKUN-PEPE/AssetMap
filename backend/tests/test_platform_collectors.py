import pytest

from app.services.collectors.fofa import FOFACollector
from app.services.collectors.hunter import HunterCollector
from app.services.collectors.quake import QuakeCollector
from app.services.collectors.zoomeye import ZoomEyeCollector


@pytest.mark.asyncio
async def test_fofa_test_connection_requires_email_and_key():
    collector = FOFACollector()

    with pytest.raises(ValueError, match="FOFA email 未配置"):
        await collector.test_connection({})

    with pytest.raises(ValueError, match="FOFA API Key 未配置"):
        await collector.test_connection({"fofa_email": "user@example.com"})


@pytest.mark.asyncio
async def test_hunter_test_connection_requires_api_key():
    collector = HunterCollector()

    with pytest.raises(ValueError, match="Hunter API Key 未配置"):
        await collector.test_connection({})


@pytest.mark.asyncio
async def test_hunter_test_connection_raises_when_body_code_is_not_success(monkeypatch):
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

    with pytest.raises(RuntimeError, match="API KEY 无效"):
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

    with pytest.raises(RuntimeError, match="API KEY 无效"):
        await collector.run("ip=\"1.1.1.1\"", {}, {"hunter_api_key": "bad"})


@pytest.mark.asyncio
async def test_zoomeye_test_connection_requires_api_key():
    collector = ZoomEyeCollector()

    with pytest.raises(ValueError, match="ZoomEye API Key 未配置"):
        await collector.test_connection({})


@pytest.mark.asyncio
async def test_zoomeye_test_connection_raises_when_body_has_error(monkeypatch):
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

    monkeypatch.setattr("app.services.collectors.zoomeye.httpx.AsyncClient", lambda *args, **kwargs: FakeClient())

    with pytest.raises(RuntimeError, match="Invalid API key"):
        await collector.test_connection({"zoomeye_api_key": "bad"})


@pytest.mark.asyncio
async def test_zoomeye_test_connection_fallback_to_org_when_ai_returns_login_required(monkeypatch):
    collector = ZoomEyeCollector()
    calls = []

    class AiResponse:
        status_code = 401

        def raise_for_status(self):
            return None

        def json(self):
            return {"code": "login_required", "error": "login required, missing Authorization header"}

    class OrgResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"code": 60000}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, **kwargs):
            calls.append(url)
            if url.startswith("https://api.zoomeye.ai"):
                return AiResponse()
            return OrgResponse()

    monkeypatch.setattr("app.services.collectors.zoomeye.httpx.AsyncClient", lambda *args, **kwargs: FakeClient())

    ok = await collector.test_connection({"zoomeye_api_key": "good"})
    assert ok is True
    assert calls == [
        "https://api.zoomeye.ai/resources-info",
        "https://api.zoomeye.org/resources-info",
    ]


@pytest.mark.asyncio
async def test_zoomeye_run_raises_friendly_message_when_credits_insufficent(monkeypatch):
    collector = ZoomEyeCollector()

    class AiResponse:
        status_code = 401

        def json(self):
            return {"code": "login_required", "error": "login required, missing Authorization header"}

    class OrgResponse:
        status_code = 402

        def json(self):
            return {
                "code": "credits_insufficent",
                "message": "request invalid, validate usage and try again",
                "error": "resource credits is insufficent",
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, **kwargs):
            if url.startswith("https://api.zoomeye.ai"):
                return AiResponse()
            return OrgResponse()

    monkeypatch.setattr("app.services.collectors.zoomeye.httpx.AsyncClient", lambda *args, **kwargs: FakeClient())

    with pytest.raises(RuntimeError, match="ZoomEye 查询额度不足"):
        await collector.run('app:"nginx"', {}, {"zoomeye_api_key": "good"})


@pytest.mark.asyncio
async def test_quake_test_connection_requires_api_key():
    collector = QuakeCollector()

    with pytest.raises(ValueError, match="Quake API Key 未配置"):
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

        async def get(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.services.collectors.quake.httpx.AsyncClient", lambda *args, **kwargs: FakeClient())

    with pytest.raises(RuntimeError, match="Invalid token"):
        await collector.test_connection({"quake_api_key": "bad"})


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

    monkeypatch.setattr("app.services.collectors.zoomeye.httpx.AsyncClient", lambda *args, **kwargs: FakeClient())

    results = await collector.run('ip="1.1.1.1"', {"limit": 1}, {"zoomeye_api_key": "secret"})

    assert results[0]["host"] == "1.1.1.1"
    assert results[0]["domain"] is None


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
                "results": [["1.1.1.1", 443, "https", "demo.example.com", "demo.example.com", "Demo", "nginx", "CN", "Beijing", "Example Org", "https://demo.example.com"]],
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
                        "site": {"host": "demo.example.com", "domain": "demo.example.com", "title": "Demo", "url": "https://demo.example.com", "server": "nginx"},
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

        async def request(self, _method, _url, params=None, **_kwargs):
            seen_pages.append(params["page"])
            return FakeResponse()

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
