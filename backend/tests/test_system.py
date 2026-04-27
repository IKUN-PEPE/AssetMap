from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import system as system_api
from app.models import SystemConfig
from app.services.system_service import DEFAULT_CONFIGS, SystemConfigService

app = FastAPI()
app.include_router(system_api.router, prefix="/api/v1/system")
client = TestClient(app)


class FakeSelectQuery:
    def __init__(self, keys):
        self.keys = keys

    def all(self):
        return [(key,) for key in self.keys]


class FakeConfigQuery:
    def __init__(self, items):
        self.items = items

    def order_by(self, *_args, **_kwargs):
        return self

    def all(self):
        return self.items


class FakeSession:
    def __init__(self, keys):
        self.keys = keys
        self.added = []
        self.commits = 0

    def query(self, target):
        assert target is SystemConfig.config_key
        return FakeSelectQuery(self.keys)

    def add_all(self, items):
        self.added.extend(items)

    def commit(self):
        self.commits += 1


def test_system_list_endpoint_masks_sensitive_values(monkeypatch):
    fake_items = [
        SimpleNamespace(
            id="1",
            config_key="hunter_api_key",
            config_value="real-secret",
            config_group="hunter",
            is_sensitive=True,
            updated_at="2026-04-20T00:00:00",
        ),
        SimpleNamespace(
            id="2",
            config_key="hunter_username",
            config_value="admin@example.com",
            config_group="hunter",
            is_sensitive=False,
            updated_at="2026-04-20T00:00:00",
        ),
    ]
    monkeypatch.setattr(system_api.SystemConfigService, "init_defaults", lambda _db: None)
    monkeypatch.setattr(system_api.SystemConfigService, "get_all_configs", lambda _db: fake_items)
    app.dependency_overrides[system_api.get_db] = lambda: object()
    try:
        response = client.get("/api/v1/system/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert body[0]["config_value"] == "******"
    assert body[1]["config_value"] == "admin@example.com"


def test_system_list_endpoint_can_reveal_sensitive_values(monkeypatch):
    fake_items = [
        SimpleNamespace(
            id="1",
            config_key="hunter_api_key",
            config_value="real-secret",
            config_group="hunter",
            is_sensitive=True,
            updated_at="2026-04-20T00:00:00",
        )
    ]
    monkeypatch.setattr(system_api.SystemConfigService, "init_defaults", lambda _db: None)
    monkeypatch.setattr(system_api.SystemConfigService, "get_all_configs", lambda _db: fake_items)
    app.dependency_overrides[system_api.get_db] = lambda: object()
    try:
        response = client.get("/api/v1/system/?reveal_sensitive=true")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()[0]["config_value"] == "real-secret"


def test_test_connection_endpoint_merges_masked_values(monkeypatch):
    captured = {}

    class FakeCollector:
        async def test_connection(self, config):
            captured.update(config)
            return True

    monkeypatch.setattr(system_api, "get_collector", lambda _platform: FakeCollector())
    monkeypatch.setattr(
        system_api.SystemConfigService,
        "get_decrypted_configs",
        lambda _db, _platform: {"hunter_api_key": "real-secret", "hunter_username": "old-user"},
    )
    app.dependency_overrides[system_api.get_db] = lambda: object()
    try:
        response = client.post(
            "/api/v1/system/test-connection",
            json={
                "platform": "hunter",
                "config": {"hunter_api_key": "******", "hunter_username": "new-user"},
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"success": True, "platform": "hunter"}
    assert captured == {"hunter_api_key": "real-secret", "hunter_username": "new-user"}


def test_init_endpoint_returns_success_message(monkeypatch):
    called = {"value": False}

    def fake_init_defaults(_db):
        called["value"] = True

    monkeypatch.setattr(system_api.SystemConfigService, "init_defaults", fake_init_defaults)
    app.dependency_overrides[system_api.get_db] = lambda: object()
    try:
        response = client.post("/api/v1/system/init")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"message": "Default configs initialized"}
    assert called["value"] is True


def test_init_defaults_only_inserts_missing_rows():
    existing_keys = {"fofa_email", "fofa_key"}
    session = FakeSession(existing_keys)

    SystemConfigService.init_defaults(session)

    inserted_keys = {item.config_key for item in session.added}
    expected_missing = {key for key, *_rest in DEFAULT_CONFIGS if key not in existing_keys}
    assert inserted_keys == expected_missing
    assert session.commits == 1


def test_init_defaults_skips_commit_when_nothing_missing():
    session = FakeSession({key for key, *_rest in DEFAULT_CONFIGS})

    SystemConfigService.init_defaults(session)

    assert session.added == []
    assert session.commits == 0
