from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.routes import investigations as investigations_route
from app.main import app
from app.schemas.trust_certificate import (
    TrustCertificate,
    TrustCertificateLifecycleEvent,
)


def _make_certificate() -> TrustCertificate:
    return TrustCertificate(
        certificate_id="cert_status_card_test",
        case_id="case_status_card_test",
        lifecycle_status="active",
        lifecycle_events=[
            TrustCertificateLifecycleEvent(
                event_type="issued",
                status_before=None,
                status_after="active",
                reason="Certificate issued after completed investigation.",
                metadata={},
            ),
            TrustCertificateLifecycleEvent(
                event_type="reverified",
                status_before="active",
                status_after="active",
                reason="Stable re-verification.",
                metadata={
                    "previous_verdict": "contradicted",
                    "fresh_verdict": "contradicted",
                    "verdict_changed": False,
                    "previous_trust_index": 0.6451,
                    "fresh_trust_index": 0.6451,
                    "trust_drop": 0.0,
                },
            ),
        ],
        overall_verdict="contradicted",
        confidence=0.6932,
        trust_index=0.6451,
        claims=[],
        evidence=[],
        sources=[],
        independence_clusters=[],
        evidence_graph_id="graph_status_card_test",
        evidence_graph_summary={},
        summary={
            "claim_count": 1,
            "evidence_count": 3,
            "source_count": 2,
            "independence_cluster_count": 2,
            "verdict_count": 1,
        },
    )


def test_status_card_endpoint_returns_frontend_ready_card(monkeypatch):
    certificate = _make_certificate()

    class FakeInvestigationService:
        def get_result(self, case_id: str):
            assert case_id == "case_status_card_test"
            return SimpleNamespace(trust_certificate=certificate)

    monkeypatch.setattr(
        investigations_route,
        "investigation_service",
        FakeInvestigationService(),
    )

    client = TestClient(app)
    response = client.get(
        "/api/v1/cases/case_status_card_test/trust-certificate/status-card"
    )

    assert response.status_code == 200

    data = response.json()
    assert data["certificate_id"] == "cert_status_card_test"
    assert data["case_id"] == "case_status_card_test"
    assert data["lifecycle_status"] == "active"
    assert data["status_label"] == "Active"
    assert data["action_required"] == "none"
    assert data["overall_verdict"] == "contradicted"
    assert data["trust_index"] == 0.6451
    assert data["claim_count"] == 1
    assert data["evidence_count"] == 3
    assert data["source_count"] == 2
    assert data["independence_cluster_count"] == 2
    assert data["event_count"] == 2
    assert data["has_been_reverified"] is True
    assert data["latest_event_type"] == "reverified"
    assert data["latest_reverification_event_type"] == "reverified"
    assert len(data["timeline"]) == 2
    assert data["timeline"][1]["is_reverification_event"] is True
