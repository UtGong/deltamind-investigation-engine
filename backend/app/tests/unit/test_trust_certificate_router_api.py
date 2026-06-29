from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.routes import trust_certificates as trust_certificates_route
from app.main import app
from app.schemas.trust_certificate import (
    TrustCertificate,
    TrustCertificateLifecycleEvent,
)


def _make_certificate() -> TrustCertificate:
    return TrustCertificate(
        certificate_id="cert_router_test",
        case_id="case_router_test",
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
        evidence_graph_id="graph_router_test",
        evidence_graph_summary={},
        summary={
            "claim_count": 1,
            "evidence_count": 3,
            "source_count": 2,
            "independence_cluster_count": 2,
            "verdict_count": 1,
        },
    )


class FakeInvestigationService:
    def __init__(self, certificate: TrustCertificate):
        self.certificate = certificate

    def get_result(self, case_id: str):
        assert case_id == "case_router_test"
        return SimpleNamespace(trust_certificate=self.certificate)


class FakeRegistry:
    def list_recent(self, *, limit: int = 20):
        return [SimpleNamespace(case_id="case_router_test")]


def test_clean_get_certificate_endpoint(monkeypatch):
    certificate = _make_certificate()

    monkeypatch.setattr(
        trust_certificates_route,
        "investigation_service",
        FakeInvestigationService(certificate),
    )

    client = TestClient(app)
    response = client.get("/api/v1/trust-certificates/case_router_test")

    assert response.status_code == 200
    data = response.json()
    assert data["certificate_id"] == "cert_router_test"
    assert data["case_id"] == "case_router_test"
    assert data["lifecycle_status"] == "active"
    assert data["overall_verdict"] == "contradicted"


def test_clean_status_card_endpoint(monkeypatch):
    certificate = _make_certificate()

    monkeypatch.setattr(
        trust_certificates_route,
        "investigation_service",
        FakeInvestigationService(certificate),
    )

    client = TestClient(app)
    response = client.get("/api/v1/trust-certificates/case_router_test/status-card")

    assert response.status_code == 200
    data = response.json()
    assert data["certificate_id"] == "cert_router_test"
    assert data["status_label"] == "Active"
    assert data["action_required"] == "none"
    assert data["has_been_reverified"] is True
    assert data["latest_reverification_event_type"] == "reverified"
    assert len(data["timeline"]) == 2


def test_clean_recent_status_cards_and_dashboard_summary(monkeypatch):
    certificate = _make_certificate()

    monkeypatch.setattr(
        trust_certificates_route,
        "investigation_service",
        FakeInvestigationService(certificate),
    )
    monkeypatch.setattr(
        trust_certificates_route,
        "trust_certificate_registry",
        FakeRegistry(),
    )

    client = TestClient(app)

    cards_response = client.get("/api/v1/trust-certificates/recent/status-cards?limit=5")
    assert cards_response.status_code == 200

    cards = cards_response.json()
    assert len(cards) == 1
    assert cards[0]["certificate_id"] == "cert_router_test"
    assert cards[0]["action_required"] == "none"

    summary_response = client.get(
        "/api/v1/trust-certificates/recent/dashboard-summary?limit=5"
    )
    assert summary_response.status_code == 200

    summary = summary_response.json()
    assert summary["certificate_count"] == 1
    assert summary["active_count"] == 1
    assert summary["stable_count"] == 1
    assert summary["average_trust_index"] == 0.6451


def _make_certificate_with_status(
    *,
    certificate_id: str,
    case_id: str,
    lifecycle_status: str,
    trust_index: float,
    reverified: bool,
) -> TrustCertificate:
    events = [
        TrustCertificateLifecycleEvent(
            event_type="issued",
            status_before=None,
            status_after="active",
            reason="Certificate issued after completed investigation.",
            metadata={},
        )
    ]

    if lifecycle_status == "revoked":
        events.append(
            TrustCertificateLifecycleEvent(
                event_type="downgrade_simulated",
                status_before="active",
                status_after="revoked",
                reason="Certificate revoked during test.",
                metadata={},
            )
        )

    if reverified:
        events.append(
            TrustCertificateLifecycleEvent(
                event_type="reverified",
                status_before=lifecycle_status,
                status_after=lifecycle_status,
                reason="Stable re-verification.",
                metadata={
                    "previous_verdict": "contradicted",
                    "fresh_verdict": "contradicted",
                    "verdict_changed": False,
                    "previous_trust_index": trust_index,
                    "fresh_trust_index": trust_index,
                    "trust_drop": 0.0,
                },
            )
        )

    return TrustCertificate(
        certificate_id=certificate_id,
        case_id=case_id,
        lifecycle_status=lifecycle_status,
        lifecycle_events=events,
        overall_verdict="contradicted",
        confidence=0.7,
        trust_index=trust_index,
        claims=[],
        evidence=[],
        sources=[],
        independence_clusters=[],
        evidence_graph_id=None,
        evidence_graph_summary={},
        summary={
            "claim_count": 1,
            "evidence_count": 3,
            "source_count": 2,
            "independence_cluster_count": 2,
            "verdict_count": 1,
        },
    )


class FakeMultiInvestigationService:
    def __init__(self, certificates: dict[str, TrustCertificate]):
        self.certificates = certificates

    def get_result(self, case_id: str):
        return SimpleNamespace(trust_certificate=self.certificates[case_id])


class FakeMultiRegistry:
    def __init__(self, case_ids: list[str]):
        self.case_ids = case_ids

    def list_recent(self, *, limit: int = 20):
        return [SimpleNamespace(case_id=case_id) for case_id in self.case_ids[:limit]]


def test_recent_status_cards_filters(monkeypatch):
    certificates = {
        "case_active_reverified": _make_certificate_with_status(
            certificate_id="cert_active_reverified",
            case_id="case_active_reverified",
            lifecycle_status="active",
            trust_index=0.8,
            reverified=True,
        ),
        "case_active_pending": _make_certificate_with_status(
            certificate_id="cert_active_pending",
            case_id="case_active_pending",
            lifecycle_status="active",
            trust_index=0.7,
            reverified=False,
        ),
        "case_revoked": _make_certificate_with_status(
            certificate_id="cert_revoked",
            case_id="case_revoked",
            lifecycle_status="revoked",
            trust_index=0.4,
            reverified=False,
        ),
    }

    monkeypatch.setattr(
        trust_certificates_route,
        "investigation_service",
        FakeMultiInvestigationService(certificates),
    )
    monkeypatch.setattr(
        trust_certificates_route,
        "trust_certificate_registry",
        FakeMultiRegistry(list(certificates.keys())),
    )

    client = TestClient(app)

    active_response = client.get(
        "/api/v1/trust-certificates/recent/status-cards?limit=10&lifecycle_status=active"
    )
    assert active_response.status_code == 200
    active_cards = active_response.json()
    assert len(active_cards) == 2
    assert {card["lifecycle_status"] for card in active_cards} == {"active"}

    reverified_response = client.get(
        "/api/v1/trust-certificates/recent/status-cards?limit=10&has_been_reverified=true"
    )
    assert reverified_response.status_code == 200
    reverified_cards = reverified_response.json()
    assert len(reverified_cards) == 1
    assert reverified_cards[0]["certificate_id"] == "cert_active_reverified"

    trust_response = client.get(
        "/api/v1/trust-certificates/recent/status-cards?limit=10&min_trust_index=0.75"
    )
    assert trust_response.status_code == 200
    trust_cards = trust_response.json()
    assert len(trust_cards) == 1
    assert trust_cards[0]["trust_index"] == 0.8


def test_dashboard_summary_filters(monkeypatch):
    certificates = {
        "case_active_reverified": _make_certificate_with_status(
            certificate_id="cert_active_reverified",
            case_id="case_active_reverified",
            lifecycle_status="active",
            trust_index=0.8,
            reverified=True,
        ),
        "case_active_pending": _make_certificate_with_status(
            certificate_id="cert_active_pending",
            case_id="case_active_pending",
            lifecycle_status="active",
            trust_index=0.7,
            reverified=False,
        ),
        "case_revoked": _make_certificate_with_status(
            certificate_id="cert_revoked",
            case_id="case_revoked",
            lifecycle_status="revoked",
            trust_index=0.4,
            reverified=False,
        ),
    }

    monkeypatch.setattr(
        trust_certificates_route,
        "investigation_service",
        FakeMultiInvestigationService(certificates),
    )
    monkeypatch.setattr(
        trust_certificates_route,
        "trust_certificate_registry",
        FakeMultiRegistry(list(certificates.keys())),
    )

    client = TestClient(app)

    response = client.get(
        "/api/v1/trust-certificates/recent/dashboard-summary?limit=10&lifecycle_status=active"
    )
    assert response.status_code == 200

    summary = response.json()
    assert summary["certificate_count"] == 2
    assert summary["active_count"] == 2
    assert summary["revoked_count"] == 0
    assert summary["filters"]["lifecycle_status"] == "active"
    assert summary["average_trust_index"] == 0.75
