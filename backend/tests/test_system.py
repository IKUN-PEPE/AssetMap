from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_system_config_endpoint():
    response = client.get("/api/v1/system/config")
    assert response.status_code == 200
    data = response.json()
    assert "sample_mode" in data
    assert "database_url" in data
