from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_cors_exposes_content_disposition_header():
    response = client.get(
        "/health",
        headers={"Origin": "http://127.0.0.1:5173"},
    )

    assert response.status_code == 200
    assert "Content-Disposition" in response.headers["access-control-expose-headers"]
