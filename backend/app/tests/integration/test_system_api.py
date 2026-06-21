from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_get_system_status():
    response = client.get("/api/v1/system/status")

    assert response.status_code == 200

    data = response.json()
    assert data["app_name"] == "DeltaMind Verify API"
    assert data["app_version"] == "0.1.0"
    assert data["llm_provider"] == "mock"
    assert data["search_planner_provider"] == "llm"
    assert "verified_claim_db_path" in data
    assert data["free_search_provider"] == "mock_search_provider"
    assert data["paid_search_provider"] == "tavily"
    assert data["allow_paid_search"] is False
    assert data["max_paid_search_calls_per_case"] == 0
