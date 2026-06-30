from fastapi import APIRouter, HTTPException, status

from app.domain.investigations.service import investigation_service
from app.domain.trust_certificates.registry import trust_certificate_registry
from app.domain.trust_certificates.lifecycle import trust_certificate_lifecycle
from app.domain.trust_certificates.status_card import build_trust_certificate_status_card
from app.schemas.trust_certificate import TrustCertificateStatusCard, TrustCertificateTimelineEvent

router = APIRouter(prefix="/cases", tags=["investigations"])


@router.post("/{case_id}/investigate")
def investigate_case(case_id: str):
    try:
        return investigation_service.investigate_case(case_id)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "Investigation failed due to an unhandled backend error.",
                "case_id": case_id,
                "error_type": type(error).__name__,
                "error_message": str(error),
            },
        ) from error


@router.get("/{case_id}/investigation")
def get_investigation_result(case_id: str):
    return investigation_service.get_result(case_id)


@router.get("/{case_id}/evidence-graph")
def get_evidence_graph(case_id: str):
    result = investigation_service.get_result(case_id)
    evidence_graph = result.evidence_graph

    if evidence_graph is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": "Evidence graph is not available for this case.",
                "case_id": case_id,
            },
        )

    return evidence_graph


@router.get("/{case_id}/trust-certificate", deprecated=True)
def get_trust_certificate(case_id: str):
    result = investigation_service.get_result(case_id)
    trust_certificate = result.trust_certificate

    if trust_certificate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": "Trust certificate is not available for this case.",
                "case_id": case_id,
            },
        )

    return trust_certificate


@router.get("/trust-certificates")
def list_trust_certificates(limit: int = 20):
    return trust_certificate_registry.list_recent(limit=limit)


@router.get("/trust-certificates/recent", deprecated=True)
def list_recent_trust_certificates(limit: int = 20):
    return trust_certificate_registry.list_recent(limit=limit)


@router.post("/{case_id}/trust-certificate/simulate-downgrade", deprecated=True)
def simulate_trust_certificate_downgrade(case_id: str, payload: dict | None = None):
    result = investigation_service.get_result(case_id)
    trust_certificate = result.trust_certificate

    if trust_certificate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": "Trust certificate is not available for this case.",
                "case_id": case_id,
            },
        )

    payload = payload or {}
    metadata = payload.get("metadata") or {}

    if not isinstance(metadata, dict):
        metadata = {}

    reason = payload.get("reason") or "Simulated downgrade caused by later conflicting evidence."

    return trust_certificate_lifecycle.simulate_downgrade(
        trust_certificate,
        reason=str(reason),
        metadata={
            "case_id": case_id,
            **metadata,
        },
    )


@router.post("/{case_id}/trust-certificate/downgrade", deprecated=True)
def downgrade_trust_certificate(case_id: str, payload: dict | None = None):
    result = investigation_service.get_result(case_id)
    trust_certificate = result.trust_certificate

    if trust_certificate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": "Trust certificate is not available for this case.",
                "case_id": case_id,
            },
        )

    payload = payload or {}
    metadata = payload.get("metadata") or {}

    if not isinstance(metadata, dict):
        metadata = {}

    reason = payload.get("reason") or "Certificate downgraded after re-verification."

    downgraded_certificate = trust_certificate_lifecycle.simulate_downgrade(
        trust_certificate,
        reason=str(reason),
        metadata={
            "case_id": case_id,
            "persistent": True,
            **metadata,
        },
    )

    return trust_certificate_lifecycle.persist_certificate_update(
        case_id=case_id,
        certificate=downgraded_certificate,
    )


@router.get("/{case_id}/trust-certificate/lifecycle", deprecated=True)
def get_trust_certificate_lifecycle(case_id: str):
    result = investigation_service.get_result(case_id)
    trust_certificate = result.trust_certificate

    if trust_certificate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": "Trust certificate is not available for this case.",
                "case_id": case_id,
            },
        )

    return {
        "certificate_id": trust_certificate.certificate_id,
        "case_id": trust_certificate.case_id,
        "lifecycle_status": trust_certificate.lifecycle_status,
        "issued_at": trust_certificate.issued_at,
        "updated_at": trust_certificate.updated_at,
        "event_count": len(trust_certificate.lifecycle_events),
        "events": trust_certificate.lifecycle_events,
    }


@router.post("/{case_id}/trust-certificate/reactivate", deprecated=True)
def reactivate_trust_certificate(case_id: str, payload: dict | None = None):
    result = investigation_service.get_result(case_id)
    trust_certificate = result.trust_certificate

    if trust_certificate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": "Trust certificate is not available for this case.",
                "case_id": case_id,
            },
        )

    payload = payload or {}
    metadata = payload.get("metadata") or {}

    if not isinstance(metadata, dict):
        metadata = {}

    reason = payload.get("reason") or "Certificate reactivated after successful re-verification."

    reactivated_certificate = trust_certificate_lifecycle.reactivate_certificate(
        trust_certificate,
        reason=str(reason),
        metadata={
            "case_id": case_id,
            "persistent": True,
            **metadata,
        },
    )

    return trust_certificate_lifecycle.persist_certificate_update(
        case_id=case_id,
        certificate=reactivated_certificate,
    )


@router.post("/{case_id}/trust-certificate/reverify", deprecated=True)
def reverify_trust_certificate(case_id: str, payload: dict | None = None):
    previous_result = investigation_service.get_result(case_id)
    previous_certificate = previous_result.trust_certificate

    if previous_certificate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": "Trust certificate is not available for this case.",
                "case_id": case_id,
            },
        )

    payload = payload or {}
    metadata = payload.get("metadata") or {}

    if not isinstance(metadata, dict):
        metadata = {}

    reason = payload.get("reason") or "Certificate re-verified by rerunning the investigation."

    trust_drop_threshold = float(payload.get("trust_drop_threshold", 0.15))
    minimum_active_trust_index = float(payload.get("minimum_active_trust_index", 0.5))

    fresh_result = investigation_service.investigate_case(case_id)
    fresh_certificate = fresh_result.trust_certificate

    if fresh_certificate is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "Fresh investigation completed without a trust certificate.",
                "case_id": case_id,
            },
        )

    reverified_certificate = trust_certificate_lifecycle.reconcile_reverification(
        previous_certificate=previous_certificate,
        fresh_certificate=fresh_certificate,
        reason=str(reason),
        metadata={
            "case_id": case_id,
            "persistent": True,
            "reverification": True,
            **metadata,
        },
        trust_drop_threshold=trust_drop_threshold,
        minimum_active_trust_index=minimum_active_trust_index,
    )

    return trust_certificate_lifecycle.persist_certificate_update(
        case_id=case_id,
        certificate=reverified_certificate,
    )


@router.get("/{case_id}/trust-certificate/reverification-summary", deprecated=True)
def get_trust_certificate_reverification_summary(case_id: str):
    result = investigation_service.get_result(case_id)
    trust_certificate = result.trust_certificate

    if trust_certificate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": "Trust certificate is not available for this case.",
                "case_id": case_id,
            },
        )

    events = list(trust_certificate.lifecycle_events or [])
    latest_event = events[-1] if events else None

    reverify_events = [
        event for event in events
        if str(event.event_type).startswith("reverification")
        or event.event_type == "reverified"
    ]
    latest_reverify_event = reverify_events[-1] if reverify_events else None

    latest_metadata = latest_event.metadata if latest_event else {}
    latest_reverify_metadata = latest_reverify_event.metadata if latest_reverify_event else {}

    return {
        "certificate_id": trust_certificate.certificate_id,
        "case_id": trust_certificate.case_id,
        "lifecycle_status": trust_certificate.lifecycle_status,
        "overall_verdict": trust_certificate.overall_verdict,
        "confidence": trust_certificate.confidence,
        "trust_index": trust_certificate.trust_index,
        "issued_at": trust_certificate.issued_at,
        "updated_at": trust_certificate.updated_at,
        "event_count": len(events),
        "has_been_reverified": latest_reverify_event is not None,
        "latest_event": None if latest_event is None else {
            "event_type": latest_event.event_type,
            "event_time": latest_event.event_time,
            "status_before": latest_event.status_before,
            "status_after": latest_event.status_after,
            "reason": latest_event.reason,
            "metadata": latest_metadata,
        },
        "latest_reverification": None if latest_reverify_event is None else {
            "event_type": latest_reverify_event.event_type,
            "event_time": latest_reverify_event.event_time,
            "status_before": latest_reverify_event.status_before,
            "status_after": latest_reverify_event.status_after,
            "reason": latest_reverify_event.reason,
            "previous_verdict": latest_reverify_metadata.get("previous_verdict"),
            "fresh_verdict": latest_reverify_metadata.get("fresh_verdict"),
            "verdict_changed": latest_reverify_metadata.get("verdict_changed"),
            "previous_trust_index": latest_reverify_metadata.get("previous_trust_index"),
            "fresh_trust_index": latest_reverify_metadata.get("fresh_trust_index"),
            "trust_drop": latest_reverify_metadata.get("trust_drop"),
            "trust_drop_threshold": latest_reverify_metadata.get("trust_drop_threshold"),
            "minimum_active_trust_index": latest_reverify_metadata.get("minimum_active_trust_index"),
        },
    }


@router.get("/{case_id}/trust-certificate/status-card", deprecated=True)
def get_trust_certificate_status_card(case_id: str):
    result = investigation_service.get_result(case_id)
    trust_certificate = result.trust_certificate

    if trust_certificate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": "Trust certificate is not available for this case.",
                "case_id": case_id,
            },
        )

    return build_trust_certificate_status_card(trust_certificate)


@router.get("/trust-certificates/recent/status-cards", deprecated=True)
def list_recent_trust_certificate_status_cards(limit: int = 20):
    registry_items = trust_certificate_registry.list_recent(limit=limit)
    cards = []

    for item in registry_items:
        result = investigation_service.get_result(item.case_id)
        trust_certificate = result.trust_certificate

        if trust_certificate is None:
            continue

        if isinstance(trust_certificate, dict):
            trust_certificate = TrustCertificate.model_validate(trust_certificate)

        cards.append(build_trust_certificate_status_card(trust_certificate))

    return cards


@router.get("/trust-certificates/recent/dashboard-summary", deprecated=True)
def get_recent_trust_certificate_dashboard_summary(limit: int = 20):
    registry_items = trust_certificate_registry.list_recent(limit=limit)
    cards = []

    for item in registry_items:
        result = investigation_service.get_result(item.case_id)
        trust_certificate = result.trust_certificate

        if trust_certificate is None:
            continue

        if isinstance(trust_certificate, dict):
            trust_certificate = TrustCertificate.model_validate(trust_certificate)

        cards.append(build_trust_certificate_status_card(trust_certificate))

    by_lifecycle_status = {}
    by_action_required = {}

    for card in cards:
        lifecycle_status = str(card.lifecycle_status)
        action_required = str(card.action_required)

        by_lifecycle_status[lifecycle_status] = by_lifecycle_status.get(lifecycle_status, 0) + 1
        by_action_required[action_required] = by_action_required.get(action_required, 0) + 1

    trust_values = [float(card.trust_index or 0.0) for card in cards]
    average_trust_index = (
        round(sum(trust_values) / len(trust_values), 4)
        if trust_values
        else 0.0
    )

    return {
        "requested_limit": limit,
        "certificate_count": len(cards),
        "by_lifecycle_status": by_lifecycle_status,
        "by_action_required": by_action_required,
        "active_count": by_lifecycle_status.get("active", 0),
        "revoked_count": by_lifecycle_status.get("revoked", 0),
        "draft_count": by_lifecycle_status.get("draft", 0),
        "review_required_count": by_action_required.get("review_required", 0),
        "reverify_available_count": by_action_required.get("reverify_available", 0),
        "stable_count": by_action_required.get("none", 0),
        "average_trust_index": average_trust_index,
    }
