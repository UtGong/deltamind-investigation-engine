from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_database_health_endpoint_returns_status_shape():
    response = client.get("/api/v1/database/health")

    assert response.status_code == 200

    data = response.json()

    assert "database_backend" in data
    assert "database_url_configured" in data
    assert "connected" in data
    assert "pgvector_enabled" in data
    assert "error" in data
