from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_llm_cache_stats():
    response = client.get("/api/v1/llm-cache/stats")

    assert response.status_code == 200
    data = response.json()

    assert "entry_count" in data
    assert "total_hits" in data
    assert "db_path" in data


def test_clear_llm_cache():
    response = client.delete("/api/v1/llm-cache")

    assert response.status_code == 200
    assert response.json()["cleared"] is True
