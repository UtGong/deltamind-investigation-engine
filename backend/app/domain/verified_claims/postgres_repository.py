import hashlib

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.constants import ClaimType, VerdictLabel
from app.db.models import VerifiedClaimRecord as DBVerifiedClaimRecord
from app.db.session import SessionLocal
from app.domain.cases.models import utc_now
from app.domain.verified_claims.freshness import (
    compute_expires_at,
    get_cache_ttl_days,
    get_freshness_policy,
    is_expired,
)
from app.domain.verified_claims.models import (
    VerifiedClaimRecord,
    normalize_claim_text,
)
from app.domain.verified_claims.repository import (
    REUSABLE_VERDICTS,
    VerifiedClaimRepository,
)
from app.schemas.agent import AtomicClaim, EvidenceItem, PivotVerdict, StanceResult


class PostgresVerifiedClaimRepository(VerifiedClaimRepository):
    def get_by_claim_text(self, claim_text: str) -> VerifiedClaimRecord | None:
        normalized = normalize_claim_text(claim_text)

        with SessionLocal() as session:
            record = session.get(DBVerifiedClaimRecord, normalized)

            if record is None:
                return None

            domain_record = self._domain_record_from_db(record)

            if is_expired(domain_record.expires_at):
                return None

            return domain_record

    def save_from_verdict(
        self,
        claim: AtomicClaim,
        verdict: PivotVerdict,
        evidence_count: int,
        evidence_items: list[EvidenceItem] | None = None,
        stance_results: list[StanceResult] | None = None,
    ) -> VerifiedClaimRecord | None:
        if verdict.verdict not in REUSABLE_VERDICTS:
            return None

        normalized = normalize_claim_text(claim.claim_text)
        now = utc_now()
        existing = self.get_by_claim_text(claim.claim_text)

        freshness_policy = get_freshness_policy(claim.claim_type)
        expires_at = compute_expires_at(claim.claim_type, now)

        evidence_snapshot = evidence_items or []
        stance_snapshot = stance_results or []

        metadata = {
            "source": "pivot_verdict",
            "reusable": True,
            "storage": "postgres",
            "ttl_days": get_cache_ttl_days(claim.claim_type),
            "evidence_snapshot_count": len(evidence_snapshot),
            "stance_snapshot_count": len(stance_snapshot),
        }

        domain_record = VerifiedClaimRecord(
            normalized_claim_text=normalized,
            claim_text=claim.claim_text,
            claim_type=claim.claim_type,
            verdict=verdict.verdict,
            confidence=verdict.confidence,
            support_score=verdict.support_score,
            contradiction_score=verdict.contradiction_score,
            uncertainty_score=verdict.uncertainty_score,
            reason=verdict.reason,
            evidence_count=evidence_count,
            freshness_policy=freshness_policy,
            expires_at=expires_at,
            evidence_snapshot=evidence_snapshot,
            stance_snapshot=stance_snapshot,
            created_at=existing.created_at if existing else now,
            updated_at=now,
            metadata=metadata,
        )

        values = {
            "normalized_claim_text": normalized,
            "claim_hash": self._hash_normalized_claim(normalized),
            "claim_text": claim.claim_text,
            "claim_type": claim.claim_type.value,
            "verdict": verdict.verdict.value,
            "confidence": verdict.confidence,
            "support_score": verdict.support_score,
            "contradiction_score": verdict.contradiction_score,
            "uncertainty_score": verdict.uncertainty_score,
            "correctness_score": None,
            "trust_score": None,
            "reason": verdict.reason,
            "evidence_count": evidence_count,
            "freshness_policy": freshness_policy,
            "expires_at": expires_at,
            "evidence_snapshot": [
                item.model_dump(mode="json") for item in evidence_snapshot
            ],
            "stance_snapshot": [
                item.model_dump(mode="json") for item in stance_snapshot
            ],
            "metadata_json": metadata,
            "updated_at": now,
        }

        statement = insert(DBVerifiedClaimRecord).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[DBVerifiedClaimRecord.normalized_claim_text],
            set_={
                "claim_hash": values["claim_hash"],
                "claim_text": values["claim_text"],
                "claim_type": values["claim_type"],
                "verdict": values["verdict"],
                "confidence": values["confidence"],
                "support_score": values["support_score"],
                "contradiction_score": values["contradiction_score"],
                "uncertainty_score": values["uncertainty_score"],
                "correctness_score": values["correctness_score"],
                "trust_score": values["trust_score"],
                "reason": values["reason"],
                "evidence_count": values["evidence_count"],
                "freshness_policy": values["freshness_policy"],
                "expires_at": values["expires_at"],
                "evidence_snapshot": values["evidence_snapshot"],
                "stance_snapshot": values["stance_snapshot"],
                "metadata_json": values["metadata_json"],
                "updated_at": now,
            },
        )

        with SessionLocal() as session:
            session.execute(statement)
            session.commit()

        return domain_record

    def list(self) -> list[VerifiedClaimRecord]:
        with SessionLocal() as session:
            records = (
                session.execute(
                    select(DBVerifiedClaimRecord).order_by(
                        DBVerifiedClaimRecord.updated_at.desc()
                    )
                )
                .scalars()
                .all()
            )

        return [self._domain_record_from_db(record) for record in records]

    def clear(self) -> None:
        with SessionLocal() as session:
            session.query(DBVerifiedClaimRecord).delete()
            session.commit()

    def _domain_record_from_db(
        self,
        record: DBVerifiedClaimRecord,
    ) -> VerifiedClaimRecord:
        evidence_snapshot = [
            EvidenceItem.model_validate(item)
            for item in (record.evidence_snapshot or [])
        ]
        stance_snapshot = [
            StanceResult.model_validate(item)
            for item in (record.stance_snapshot or [])
        ]

        return VerifiedClaimRecord(
            normalized_claim_text=record.normalized_claim_text,
            claim_text=record.claim_text or record.normalized_claim_text,
            claim_type=ClaimType(record.claim_type),
            verdict=VerdictLabel(record.verdict),
            confidence=record.confidence or 0.0,
            support_score=record.support_score or 0.0,
            contradiction_score=record.contradiction_score or 0.0,
            uncertainty_score=record.uncertainty_score or 0.0,
            reason=record.reason or "",
            evidence_count=record.evidence_count or 0,
            freshness_policy=record.freshness_policy,
            expires_at=record.expires_at,
            evidence_snapshot=evidence_snapshot,
            stance_snapshot=stance_snapshot,
            created_at=record.created_at,
            updated_at=record.updated_at,
            metadata=record.metadata_json or {},
        )

    def _hash_normalized_claim(self, normalized_claim_text: str) -> str:
        return hashlib.sha256(
            normalized_claim_text.encode("utf-8")
        ).hexdigest()
