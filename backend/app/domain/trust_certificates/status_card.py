from app.schemas.trust_certificate import (
    TrustCertificate,
    TrustCertificateStatusCard,
    TrustCertificateTimelineEvent,
)


def build_trust_certificate_status_card(
    trust_certificate: TrustCertificate,
) -> TrustCertificateStatusCard:
    events = list(trust_certificate.lifecycle_events or [])

    reverify_events = [
        event
        for event in events
        if str(event.event_type).startswith("reverification")
        or event.event_type == "reverified"
    ]

    latest_event = events[-1] if events else None
    latest_reverify_event = reverify_events[-1] if reverify_events else None

    lifecycle_status = str(trust_certificate.lifecycle_status)

    if lifecycle_status == "active":
        status_label = "Active"
        action_required = "none" if latest_reverify_event else "reverify_available"
    elif lifecycle_status == "revoked":
        status_label = "Revoked"
        action_required = "review_required"
    elif lifecycle_status == "draft":
        status_label = "Draft"
        action_required = "issue_certificate"
    else:
        status_label = lifecycle_status.title()
        action_required = "review_required"

    summary = trust_certificate.summary or {}

    timeline = [
        TrustCertificateTimelineEvent(
            event_type=event.event_type,
            event_time=event.event_time,
            status_before=event.status_before,
            status_after=event.status_after,
            reason=event.reason,
            is_reverification_event=(
                str(event.event_type).startswith("reverification")
                or event.event_type == "reverified"
            ),
            is_terminal_event=str(event.status_after) == "revoked",
            metadata=event.metadata or {},
        )
        for event in events
    ]

    return TrustCertificateStatusCard(
        certificate_id=trust_certificate.certificate_id,
        case_id=trust_certificate.case_id,
        lifecycle_status=trust_certificate.lifecycle_status,
        status_label=status_label,
        action_required=action_required,
        overall_verdict=trust_certificate.overall_verdict,
        confidence=trust_certificate.confidence,
        trust_index=trust_certificate.trust_index,
        evidence_graph_id=trust_certificate.evidence_graph_id,
        issued_at=trust_certificate.issued_at,
        updated_at=trust_certificate.updated_at,
        claim_count=summary.get("claim_count", 0),
        evidence_count=summary.get("evidence_count", 0),
        source_count=summary.get("source_count", 0),
        independence_cluster_count=summary.get("independence_cluster_count", 0),
        event_count=len(events),
        has_been_reverified=latest_reverify_event is not None,
        latest_event_type=None if latest_event is None else latest_event.event_type,
        latest_reverification_event_type=(
            None if latest_reverify_event is None else latest_reverify_event.event_type
        ),
        timeline=timeline,
    )
