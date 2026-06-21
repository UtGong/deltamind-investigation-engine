from app.core.constants import ClaimType, VerdictLabel
from app.db.session import check_database_connection
from app.domain.verified_claims.postgres_repository import (
    PostgresVerifiedClaimRepository,
)
from app.schemas.agent import AtomicClaim, PivotVerdict


def test_postgres_verified_claim_repository_roundtrip_when_database_connected():
    health = check_database_connection()

    if not health["connected"]:
        return

    repository = PostgresVerifiedClaimRepository()
    repository.clear()

    claim = AtomicClaim(
        claim_id="claim_test_1",
        claim_text="The Boston Celtics won the 2024 NBA Finals.",
        claim_type=ClaimType.RESULT,
        confidence=0.95,
    )

    verdict = PivotVerdict(
        claim_id=claim.claim_id,
        verdict=VerdictLabel.SUPPORTED,
        confidence=0.91,
        support_score=0.88,
        contradiction_score=0.02,
        uncertainty_score=0.10,
        reason="Supported by reliable evidence.",
    )

    saved = repository.save_from_verdict(
        claim=claim,
        verdict=verdict,
        evidence_count=1,
        evidence_items=[],
        stance_results=[],
    )

    assert saved is not None
    assert saved.metadata["storage"] == "postgres"

    cached = repository.get_by_claim_text(
        "The Boston Celtics won the 2024 NBA Finals."
    )

    assert cached is not None
    assert cached.verdict == VerdictLabel.SUPPORTED
    assert cached.confidence == 0.91
    assert cached.support_score == 0.88
    assert cached.evidence_count == 1

    records = repository.list()
    assert len(records) == 1

    repository.clear()
    assert repository.list() == []
