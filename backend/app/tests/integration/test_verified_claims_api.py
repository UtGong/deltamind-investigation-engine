from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_list_verified_claims():
    response = client.get("/api/v1/verified-claims")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_clear_verified_claims():
    response = client.delete("/api/v1/verified-claims")

    assert response.status_code == 200
    assert response.json()["cleared"] is True
