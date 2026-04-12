from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "env" in body


def test_health_is_unauthenticated() -> None:
    # MTC-07: /health is the only public route, no API key needed
    response = client.get("/health")
    assert response.status_code == 200
