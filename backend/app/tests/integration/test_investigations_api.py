from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_investigate_case():
    create_response = client.post(
        "/api/v1/cases",
        json={
            "input_type": "claim",
            "input_text": "Player X joined Club A on June 10.",
            "title": "Transfer claim",
        },
    )

    assert create_response.status_code == 200

    case_id = create_response.json()["case_id"]

    investigate_response = client.post(f"/api/v1/cases/{case_id}/investigate")

    assert investigate_response.status_code == 200

    data = investigate_response.json()
    assert data["case_id"] == case_id
    assert data["status"] == "completed"
    assert len(data["claims"]) >= 1

    # A raw claim should not verify itself. Evidence can be zero if no external
    # source is retrieved and no verified-claim cache hit occurs.
    assert isinstance(data["evidence"], list)
    assert isinstance(data["stances"], list)
    assert isinstance(data["verdicts"], list)

    assert data["case_verdict"] in {
        "supported",
        "contradicted",
        "partially_supported",
        "outdated",
        "misleading",
        "unverifiable",
        "contested",
        None,
    }


def test_get_investigation_result():
    create_response = client.post(
        "/api/v1/cases",
        json={
            "input_type": "claim",
            "input_text": "Player X joined Club A on June 10.",
            "title": "Transfer claim",
        },
    )

    assert create_response.status_code == 200

    case_id = create_response.json()["case_id"]

    investigate_response = client.post(f"/api/v1/cases/{case_id}/investigate")
    assert investigate_response.status_code == 200

    result_response = client.get(f"/api/v1/cases/{case_id}/investigation")

    assert result_response.status_code == 200
    assert result_response.json()["case_id"] == case_id


def test_get_missing_investigation_result_returns_404():
    response = client.get("/api/v1/cases/missing-case/investigation")

    assert response.status_code == 404
