from fastapi import APIRouter, HTTPException, status

from app.domain.investigations.service import investigation_service
from app.domain.trust_certificates.lifecycle import trust_certificate_lifecycle
from app.domain.trust_certificates.registry import trust_certificate_registry
from app.domain.trust_certificates.status_card import build_trust_certificate_status_card
from app.schemas.trust_certificate import (
    TrustCertificate,
    TrustCertificateDashboardSummary,
    TrustCertificateLifecycleResponse,
    TrustCertificateLifecycleActionRequest,
    TrustCertificateReverificationRequest,
    TrustCertificateReverificationSummary,
    TrustCertificateLatestEventSummary,
    TrustCertificateReverificationEventSummary,
    TrustCertificateRegistryItem,
    TrustCertificateStatusCard,
)


router = APIRouter(prefix="/api/v1/trust-certificates", tags=["trust-certificates"])


def _get_trust_certificate_or_404(case_id: str) -> TrustCertificate:
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

    if isinstance(trust_certificate, dict):
        trust_certificate = TrustCertificate.model_validate(trust_certificate)

    return trust_certificate


def _recent_cards(
    limit: int,
    *,
    lifecycle_status: str | None = None,
    action_required: str | None = None,
    min_trust_index: float | None = None,
    has_been_reverified: bool | None = None,
):
    limit = max(1, min(limit, 100))
    fetch_limit = min(max(limit * 3, limit), 100)

    registry_items = trust_certificate_registry.list_recent(limit=fetch_limit)
    cards = []

    for item in registry_items:
        trust_certificate = _get_trust_certificate_or_404(item.case_id)
        card = build_trust_certificate_status_card(trust_certificate)

        if lifecycle_status is not None and str(card.lifecycle_status) != lifecycle_status:
            continue

        if action_required is not None and str(card.action_required) != action_required:
            continue

        if min_trust_index is not None and float(card.trust_index or 0.0) < min_trust_index:
            continue

        if has_been_reverified is not None and card.has_been_reverified != has_been_reverified:
            continue

        cards.append(card)

        if len(cards) >= limit:
            break

    return cards


@router.get("/recent", response_model=list[TrustCertificateRegistryItem])
def list_recent_trust_certificates(limit: int = 20):
    return trust_certificate_registry.list_recent(limit=limit)


@router.get("/recent/status-cards", response_model=list[TrustCertificateStatusCard])
def list_recent_trust_certificate_status_cards(
    limit: int = 20,
    lifecycle_status: str | None = None,
    action_required: str | None = None,
    min_trust_index: float | None = None,
    has_been_reverified: bool | None = None,
):
    return _recent_cards(
        limit=limit,
        lifecycle_status=lifecycle_status,
        action_required=action_required,
        min_trust_index=min_trust_index,
        has_been_reverified=has_been_reverified,
    )


@router.get("/recent/dashboard-summary", response_model=TrustCertificateDashboardSummary)
def get_recent_trust_certificate_dashboard_summary(
    limit: int = 20,
    lifecycle_status: str | None = None,
    action_required: str | None = None,
    min_trust_index: float | None = None,
    has_been_reverified: bool | None = None,
):
    cards = _recent_cards(
        limit=limit,
        lifecycle_status=lifecycle_status,
        action_required=action_required,
        min_trust_index=min_trust_index,
        has_been_reverified=has_been_reverified,
    )

    by_lifecycle_status = {}
    by_action_required = {}

    for card in cards:
        card_lifecycle_status = str(card.lifecycle_status)
        card_action_required = str(card.action_required)

        by_lifecycle_status[card_lifecycle_status] = by_lifecycle_status.get(card_lifecycle_status, 0) + 1
        by_action_required[card_action_required] = by_action_required.get(card_action_required, 0) + 1

    trust_values = [float(card.trust_index or 0.0) for card in cards]
    average_trust_index = (
        round(sum(trust_values) / len(trust_values), 4)
        if trust_values
        else 0.0
    )

    return TrustCertificateDashboardSummary(
        requested_limit=limit,
        filters={
            "lifecycle_status": lifecycle_status,
            "action_required": action_required,
            "min_trust_index": min_trust_index,
            "has_been_reverified": has_been_reverified,
        },
        certificate_count=len(cards),
        by_lifecycle_status=by_lifecycle_status,
        by_action_required=by_action_required,
        active_count=by_lifecycle_status.get("active", 0),
        revoked_count=by_lifecycle_status.get("revoked", 0),
        draft_count=by_lifecycle_status.get("draft", 0),
        review_required_count=by_action_required.get("review_required", 0),
        reverify_available_count=by_action_required.get("reverify_available", 0),
        stable_count=by_action_required.get("none", 0),
        average_trust_index=average_trust_index,
    )


@router.get("/{case_id}", response_model=TrustCertificate)
def get_trust_certificate(case_id: str):
    return _get_trust_certificate_or_404(case_id)


@router.get("/{case_id}/status-card", response_model=TrustCertificateStatusCard)
def get_trust_certificate_status_card(case_id: str):
    trust_certificate = _get_trust_certificate_or_404(case_id)
    return build_trust_certificate_status_card(trust_certificate)


@router.get("/{case_id}/lifecycle", response_model=TrustCertificateLifecycleResponse)
def get_trust_certificate_lifecycle(case_id: str):
    trust_certificate = _get_trust_certificate_or_404(case_id)

    return TrustCertificateLifecycleResponse(
        certificate_id=trust_certificate.certificate_id,
        case_id=trust_certificate.case_id,
        lifecycle_status=trust_certificate.lifecycle_status,
        issued_at=trust_certificate.issued_at,
        updated_at=trust_certificate.updated_at,
        event_count=len(trust_certificate.lifecycle_events),
        events=trust_certificate.lifecycle_events,
    )


@router.get("/{case_id}/reverification-summary", response_model=TrustCertificateReverificationSummary)
def get_trust_certificate_reverification_summary(case_id: str):
    trust_certificate = _get_trust_certificate_or_404(case_id)

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

    return TrustCertificateReverificationSummary(
        certificate_id=trust_certificate.certificate_id,
        case_id=trust_certificate.case_id,
        lifecycle_status=trust_certificate.lifecycle_status,
        overall_verdict=trust_certificate.overall_verdict,
        confidence=trust_certificate.confidence,
        trust_index=trust_certificate.trust_index,
        issued_at=trust_certificate.issued_at,
        updated_at=trust_certificate.updated_at,
        event_count=len(events),
        has_been_reverified=latest_reverify_event is not None,
        latest_event=None if latest_event is None else TrustCertificateLatestEventSummary(
            event_type=latest_event.event_type,
            event_time=latest_event.event_time,
            status_before=latest_event.status_before,
            status_after=latest_event.status_after,
            reason=latest_event.reason,
            metadata=latest_metadata,
        ),
        latest_reverification=None if latest_reverify_event is None else TrustCertificateReverificationEventSummary(
            event_type=latest_reverify_event.event_type,
            event_time=latest_reverify_event.event_time,
            status_before=latest_reverify_event.status_before,
            status_after=latest_reverify_event.status_after,
            reason=latest_reverify_event.reason,
            previous_verdict=latest_reverify_metadata.get("previous_verdict"),
            fresh_verdict=latest_reverify_metadata.get("fresh_verdict"),
            verdict_changed=latest_reverify_metadata.get("verdict_changed"),
            previous_trust_index=latest_reverify_metadata.get("previous_trust_index"),
            fresh_trust_index=latest_reverify_metadata.get("fresh_trust_index"),
            trust_drop=latest_reverify_metadata.get("trust_drop"),
            trust_drop_threshold=latest_reverify_metadata.get("trust_drop_threshold"),
            minimum_active_trust_index=latest_reverify_metadata.get("minimum_active_trust_index"),
        ),
    )


@router.post("/{case_id}/simulate-downgrade", response_model=TrustCertificate)
def simulate_trust_certificate_downgrade(case_id: str, payload: TrustCertificateLifecycleActionRequest | None = None):
    trust_certificate = _get_trust_certificate_or_404(case_id)

    payload = payload or TrustCertificateLifecycleActionRequest()
    metadata = payload.metadata or {}

    reason = payload.reason or "Simulated downgrade caused by later conflicting evidence."

    return trust_certificate_lifecycle.simulate_downgrade(
        trust_certificate,
        reason=str(reason),
        metadata={
            "case_id": case_id,
            **metadata,
        },
    )


@router.post("/{case_id}/downgrade", response_model=TrustCertificate)
def downgrade_trust_certificate(case_id: str, payload: TrustCertificateLifecycleActionRequest | None = None):
    trust_certificate = _get_trust_certificate_or_404(case_id)

    payload = payload or TrustCertificateLifecycleActionRequest()
    metadata = payload.metadata or {}

    reason = payload.reason or "Certificate downgraded after re-verification."

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


@router.post("/{case_id}/reactivate", response_model=TrustCertificate)
def reactivate_trust_certificate(case_id: str, payload: TrustCertificateLifecycleActionRequest | None = None):
    trust_certificate = _get_trust_certificate_or_404(case_id)

    payload = payload or TrustCertificateLifecycleActionRequest()
    metadata = payload.metadata or {}

    reason = payload.reason or "Certificate reactivated after successful re-verification."

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


@router.post("/{case_id}/reverify", response_model=TrustCertificate)
def reverify_trust_certificate(case_id: str, payload: TrustCertificateReverificationRequest | None = None):
    previous_certificate = _get_trust_certificate_or_404(case_id)

    payload = payload or TrustCertificateReverificationRequest()
    metadata = payload.metadata or {}

    reason = payload.reason or "Certificate re-verified by rerunning the investigation."
    trust_drop_threshold = float(payload.trust_drop_threshold)
    minimum_active_trust_index = float(payload.minimum_active_trust_index)

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
