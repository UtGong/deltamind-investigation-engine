from app.domain.trust_certificates.lifecycle import TrustCertificateLifecycleService
from app.schemas.trust_certificate import (
    TrustCertificate,
    TrustCertificateLifecycleEvent,
)


def _make_active_certificate() -> TrustCertificate:
    return TrustCertificate(
        certificate_id="cert_lifecycle_test",
        case_id="case_lifecycle_test",
        lifecycle_status="active",
        lifecycle_events=[
            TrustCertificateLifecycleEvent(
                event_type="issued",
                status_before=None,
                status_after="active",
                reason="Certificate issued after completed investigation.",
                metadata={"source": "unit_test"},
            )
        ],
        overall_verdict="supported",
        confidence=0.82,
        trust_index=0.78,
        claims=[],
        evidence=[],
        sources=[],
        independence_clusters=[],
        evidence_graph_id=None,
        evidence_graph_summary={},
        summary={
            "claim_count": 0,
            "evidence_count": 0,
            "source_count": 0,
            "independence_cluster_count": 0,
            "verdict_count": 0,
        },
    )


def test_simulate_downgrade_marks_certificate_revoked():
    lifecycle = TrustCertificateLifecycleService()
    certificate = _make_active_certificate()

    downgraded = lifecycle.simulate_downgrade(
        certificate,
        reason="Later evidence contradicted the certificate.",
        metadata={"trigger": "unit_test"},
    )

    assert downgraded.lifecycle_status == "revoked"
    assert len(downgraded.lifecycle_events) == 2

    last_event = downgraded.lifecycle_events[-1]
    assert last_event.event_type == "downgrade_simulated"
    assert last_event.status_before == "active"
    assert last_event.status_after == "revoked"
    assert last_event.reason == "Later evidence contradicted the certificate."
    assert last_event.metadata["simulation"] is True
    assert last_event.metadata["trigger"] == "unit_test"


def test_reactivate_certificate_marks_certificate_active():
    lifecycle = TrustCertificateLifecycleService()
    certificate = _make_active_certificate()

    downgraded = lifecycle.simulate_downgrade(
        certificate,
        reason="Later evidence contradicted the certificate.",
        metadata={"trigger": "unit_test"},
    )

    reactivated = lifecycle.reactivate_certificate(
        downgraded,
        reason="Confidence restored after re-verification.",
        metadata={"review_result": "confidence_restored"},
    )

    assert reactivated.lifecycle_status == "active"
    assert len(reactivated.lifecycle_events) == 3

    last_event = reactivated.lifecycle_events[-1]
    assert last_event.event_type == "reactivated"
    assert last_event.status_before == "revoked"
    assert last_event.status_after == "active"
    assert last_event.reason == "Confidence restored after re-verification."
    assert last_event.metadata["review_result"] == "confidence_restored"

def test_reconcile_reverification_keeps_active_certificate_active():
    lifecycle = TrustCertificateLifecycleService()

    previous = _make_active_certificate()
    fresh = _make_active_certificate().model_copy(
        update={
            "certificate_id": "cert_fresh_same",
            "overall_verdict": "supported",
            "trust_index": 0.78,
        }
    )

    reverified = lifecycle.reconcile_reverification(
        previous_certificate=previous,
        fresh_certificate=fresh,
        reason="Stable re-verification.",
        metadata={"trigger": "unit_test"},
    )

    assert reverified.lifecycle_status == "active"
    assert reverified.lifecycle_events[-1].event_type == "reverified"
    assert reverified.lifecycle_events[-1].status_before == "active"
    assert reverified.lifecycle_events[-1].status_after == "active"
    assert reverified.lifecycle_events[-1].metadata["verdict_changed"] is False
    assert reverified.lifecycle_events[-1].metadata["trust_drop"] == 0.0


def test_reconcile_reverification_revokes_when_verdict_changes():
    lifecycle = TrustCertificateLifecycleService()

    previous = _make_active_certificate().model_copy(
        update={
            "overall_verdict": "supported",
            "trust_index": 0.78,
        }
    )
    fresh = _make_active_certificate().model_copy(
        update={
            "certificate_id": "cert_fresh_changed",
            "overall_verdict": "contradicted",
            "trust_index": 0.74,
        }
    )

    reverified = lifecycle.reconcile_reverification(
        previous_certificate=previous,
        fresh_certificate=fresh,
        reason="Verdict changed during re-verification.",
        metadata={"trigger": "unit_test"},
    )

    assert reverified.lifecycle_status == "revoked"
    assert reverified.lifecycle_events[-1].event_type == "reverification_downgraded"
    assert reverified.lifecycle_events[-1].status_before == "active"
    assert reverified.lifecycle_events[-1].status_after == "revoked"
    assert reverified.lifecycle_events[-1].metadata["verdict_changed"] is True


def test_reconcile_reverification_reactivates_revoked_certificate_when_stable():
    lifecycle = TrustCertificateLifecycleService()

    active = _make_active_certificate()
    revoked = lifecycle.simulate_downgrade(
        active,
        reason="Earlier downgrade.",
        metadata={"trigger": "unit_test"},
    )

    fresh = _make_active_certificate().model_copy(
        update={
            "certificate_id": "cert_fresh_restored",
            "overall_verdict": revoked.overall_verdict,
            "trust_index": revoked.trust_index,
        }
    )

    reverified = lifecycle.reconcile_reverification(
        previous_certificate=revoked,
        fresh_certificate=fresh,
        reason="Certificate restored during re-verification.",
        metadata={"trigger": "unit_test"},
    )

    assert reverified.lifecycle_status == "active"
    assert reverified.lifecycle_events[-1].event_type == "reverification_reactivated"
    assert reverified.lifecycle_events[-1].status_before == "revoked"
    assert reverified.lifecycle_events[-1].status_after == "active"

