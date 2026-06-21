from app.domain.verified_claims.models import VerifiedClaimRecord
from app.domain.verified_claims.repository import (
    VerifiedClaimRepository,
    verified_claim_repository,
)
from app.schemas.agent import AtomicClaim, EvidenceItem, PivotVerdict, StanceResult


class VerifiedClaimService:
    def __init__(self, repository: VerifiedClaimRepository) -> None:
        self.repository = repository

    def lookup(self, claim: AtomicClaim) -> VerifiedClaimRecord | None:
        return self.repository.get_by_claim_text(claim.claim_text)

    def save_if_reusable(
        self,
        claim: AtomicClaim,
        verdict: PivotVerdict,
        evidence_count: int,
        evidence_items: list[EvidenceItem] | None = None,
        stance_results: list[StanceResult] | None = None,
    ) -> VerifiedClaimRecord | None:
        return self.repository.save_from_verdict(
            claim=claim,
            verdict=verdict,
            evidence_count=evidence_count,
            evidence_items=evidence_items,
            stance_results=stance_results,
        )

    def list_records(self) -> list[VerifiedClaimRecord]:
        return self.repository.list()

    def clear(self) -> None:
        self.repository.clear()


verified_claim_service = VerifiedClaimService(verified_claim_repository)
