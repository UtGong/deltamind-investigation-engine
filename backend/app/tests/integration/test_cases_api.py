from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_create_case():
    response = client.post(
        "/api/v1/cases",
        json={
            "input_type": "claim",
            "input_text": "Player X joined Club A on June 10.",
            "title": "Transfer claim",
        },
    )

    assert response.status_code == 200

    data = response.json()
    assert data["case_id"].startswith("case_")
    assert data["title"] == "Transfer claim"
    assert data["input_type"] == "claim"
    assert data["status"] == "created"


def test_get_case_after_create():
    create_response = client.post(
        "/api/v1/cases",
        json={
            "input_type": "claim",
            "input_text": "Team A won the final.",
        },
    )

    case_id = create_response.json()["case_id"]

    get_response = client.get(f"/api/v1/cases/{case_id}")

    assert get_response.status_code == 200
    assert get_response.json()["case_id"] == case_id


def test_get_missing_case_returns_404():
    response = client.get("/api/v1/cases/case_missing")

    assert response.status_code == 404
