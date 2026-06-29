from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from app.db.models import CaseRecord
from app.db.session import SessionLocal

from app.schemas.trust_certificate import (
    TrustCertificate,
    TrustCertificateLifecycleEvent,
)


class TrustCertificateLifecycleService:
    def simulate_downgrade(
        self,
        certificate: TrustCertificate,
        *,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> TrustCertificate:
        now = datetime.now(timezone.utc)
        metadata = dict(metadata or {})
        metadata["simulation"] = True

        event = TrustCertificateLifecycleEvent(
            event_type="downgrade_simulated",
            event_time=now,
            status_before=certificate.lifecycle_status,
            status_after="revoked",
            reason=reason,
            metadata=metadata,
        )

        return certificate.model_copy(
            update={
                "lifecycle_status": "revoked",
                "updated_at": now,
                "lifecycle_events": [
                    *certificate.lifecycle_events,
                    event,
                ],
            }
        )

    
    def reactivate_certificate(
        self,
        certificate: TrustCertificate,
        *,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> TrustCertificate:
        now = datetime.now(timezone.utc)
        metadata = dict(metadata or {})

        event = TrustCertificateLifecycleEvent(
            event_type="reactivated",
            event_time=now,
            status_before=certificate.lifecycle_status,
            status_after="active",
            reason=reason,
            metadata=metadata,
        )

        return certificate.model_copy(
            update={
                "lifecycle_status": "active",
                "updated_at": now,
                "lifecycle_events": [
                    *certificate.lifecycle_events,
                    event,
                ],
            }
        )


    def reconcile_reverification(
        self,
        *,
        previous_certificate: TrustCertificate,
        fresh_certificate: TrustCertificate,
        reason: str,
        metadata: dict[str, Any] | None = None,
        trust_drop_threshold: float = 0.15,
        minimum_active_trust_index: float = 0.5,
    ) -> TrustCertificate:
        now = datetime.now(timezone.utc)
        metadata = dict(metadata or {})

        previous_verdict = str(previous_certificate.overall_verdict)
        fresh_verdict = str(fresh_certificate.overall_verdict)
        previous_trust_index = float(previous_certificate.trust_index or 0.0)
        fresh_trust_index = float(fresh_certificate.trust_index or 0.0)

        verdict_changed = previous_verdict != fresh_verdict
        trust_drop = previous_trust_index - fresh_trust_index

        should_revoke = (
            verdict_changed
            or trust_drop >= trust_drop_threshold
            or fresh_trust_index < minimum_active_trust_index
        )

        if should_revoke:
            status_after = "revoked"
            event_type = "reverification_downgraded"
        elif previous_certificate.lifecycle_status == "revoked":
            status_after = "active"
            event_type = "reverification_reactivated"
        else:
            status_after = "active"
            event_type = "reverified"

        event = TrustCertificateLifecycleEvent(
            event_type=event_type,
            event_time=now,
            status_before=previous_certificate.lifecycle_status,
            status_after=status_after,
            reason=reason,
            metadata={
                "previous_certificate_id": previous_certificate.certificate_id,
                "fresh_certificate_id": fresh_certificate.certificate_id,
                "previous_verdict": previous_verdict,
                "fresh_verdict": fresh_verdict,
                "previous_trust_index": round(previous_trust_index, 4),
                "fresh_trust_index": round(fresh_trust_index, 4),
                "verdict_changed": verdict_changed,
                "trust_drop": round(trust_drop, 4),
                "trust_drop_threshold": trust_drop_threshold,
                "minimum_active_trust_index": minimum_active_trust_index,
                **metadata,
            },
        )

        return fresh_certificate.model_copy(
            update={
                "lifecycle_status": status_after,
                "issued_at": previous_certificate.issued_at,
                "updated_at": now,
                "lifecycle_events": [
                    *previous_certificate.lifecycle_events,
                    event,
                ],
            }
        )


    def persist_certificate_update(
        self,
        *,
        case_id: str,
        certificate: TrustCertificate,
    ) -> TrustCertificate:
        with SessionLocal() as session:
            row = session.query(CaseRecord).filter(CaseRecord.case_id == case_id).one_or_none()

            if row is None:
                raise ValueError(f"Case not found: {case_id}")

            result_json = dict(row.investigation_result_json or {})
            result_json["trust_certificate"] = certificate.model_dump(mode="json")

            row.investigation_result_json = result_json
            flag_modified(row, "investigation_result_json")

            if hasattr(row, "updated_at"):
                row.updated_at = datetime.now(timezone.utc)

            session.commit()

        return certificate


trust_certificate_lifecycle = TrustCertificateLifecycleService()
