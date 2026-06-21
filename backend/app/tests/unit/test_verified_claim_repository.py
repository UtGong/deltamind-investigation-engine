from datetime import timedelta

from app.core.constants import ClaimType, VerdictLabel
from app.domain.cases.models import utc_now
from app.domain.verified_claims.repository import (
    InMemoryVerifiedClaimRepository,
    SqliteVerifiedClaimRepository,
)
from app.schemas.agent import AtomicClaim, EvidenceItem, PivotVerdict


def make_claim(claim_type: ClaimType = ClaimType.RESULT) -> AtomicClaim:
    return AtomicClaim(
        claim_id="claim_1",
        claim_text="Team A won the final 3-1.",
        claim_type=claim_type,
        confidence=0.9,
    )

def make_evidence() -> EvidenceItem:
    return EvidenceItem(
        evidence_id="evidence_1",
        claim_id="claim_1",
        source_id="source_1",
        url="https://example.com/source",
        title="Example source",
        evidence_text="Team A won the final 3-1.",
        independence_group="source_1",
        reliability=0.9,
        independence=0.8,
        freshness=0.7,
        specificity=0.95,
    )


def make_supported_verdict() -> PivotVerdict:
    return PivotVerdict(
        claim_id="claim_1",
        verdict=VerdictLabel.SUPPORTED,
        confidence=0.8,
        support_score=0.9,
        contradiction_score=0.0,
        uncertainty_score=0.1,
        reason="Supported by evidence.",
    )


def make_unverifiable_verdict() -> PivotVerdict:
    return PivotVerdict(
        claim_id="claim_1",
        verdict=VerdictLabel.UNVERIFIABLE,
        confidence=0.2,
        support_score=0.0,
        contradiction_score=0.0,
        uncertainty_score=1.0,
        reason="Not enough evidence.",
    )


def test_verified_claim_repository_saves_and_looks_up_reusable_verdict():
    repo = InMemoryVerifiedClaimRepository()

    saved = repo.save_from_verdict(
        claim=make_claim(),
        verdict=make_supported_verdict(),
        evidence_count=2,
    )

    assert saved is not None

    lookup = repo.get_by_claim_text("team a won the final 3-1")
    assert lookup is not None
    assert lookup.verdict == VerdictLabel.SUPPORTED
    assert lookup.evidence_count == 2


def test_verified_claim_repository_normalizes_case_and_punctuation():
    repo = InMemoryVerifiedClaimRepository()

    repo.save_from_verdict(
        claim=make_claim(),
        verdict=make_supported_verdict(),
        evidence_count=2,
    )

    lookup = repo.get_by_claim_text("TEAM A won the final 3-1!")
    assert lookup is not None
    assert lookup.verdict == VerdictLabel.SUPPORTED


def test_verified_claim_repository_does_not_save_unverifiable_verdict():
    repo = InMemoryVerifiedClaimRepository()

    saved = repo.save_from_verdict(
        claim=make_claim(),
        verdict=make_unverifiable_verdict(),
        evidence_count=0,
    )

    assert saved is None
    assert repo.get_by_claim_text(make_claim().claim_text) is None


def test_sqlite_verified_claim_repository_persists_records(tmp_path):
    db_path = tmp_path / "verified_claims.sqlite3"

    repo_1 = SqliteVerifiedClaimRepository(str(db_path))
    repo_1.save_from_verdict(
        claim=make_claim(),
        verdict=make_supported_verdict(),
        evidence_count=2,
    )

    repo_2 = SqliteVerifiedClaimRepository(str(db_path))
    lookup = repo_2.get_by_claim_text("team a won the final 3-1")

    assert lookup is not None
    assert lookup.verdict == VerdictLabel.SUPPORTED
    assert lookup.evidence_count == 2
    assert lookup.expires_at is not None
    assert lookup.freshness_policy == "stable_result_long_ttl"


def test_sqlite_verified_claim_repository_clear(tmp_path):
    db_path = tmp_path / "verified_claims.sqlite3"

    repo = SqliteVerifiedClaimRepository(str(db_path))
    repo.save_from_verdict(
        claim=make_claim(),
        verdict=make_supported_verdict(),
        evidence_count=2,
    )

    assert len(repo.list()) == 1

    repo.clear()

    assert repo.list() == []


def test_sqlite_verified_claim_repository_does_not_reuse_expired_record(tmp_path):
    db_path = tmp_path / "verified_claims.sqlite3"

    repo = SqliteVerifiedClaimRepository(str(db_path))
    repo.save_from_verdict(
        claim=make_claim(ClaimType.INJURY),
        verdict=make_supported_verdict(),
        evidence_count=2,
    )

    expired_at = utc_now() - timedelta(days=1)

    repo.connection.execute(
        """
        UPDATE verified_claims
        SET expires_at = ?
        WHERE normalized_claim_text = ?
        """,
        (
            expired_at.isoformat(),
            "team a won the final 3-1",
        ),
    )
    repo.connection.commit()

    lookup = repo.get_by_claim_text("team a won the final 3-1")

    assert lookup is None
    assert len(repo.list()) == 1


def test_sqlite_verified_claim_repository_persists_evidence_snapshot(tmp_path):
    db_path = tmp_path / "verified_claims.sqlite3"

    repo_1 = SqliteVerifiedClaimRepository(str(db_path))
    repo_1.save_from_verdict(
        claim=make_claim(),
        verdict=make_supported_verdict(),
        evidence_count=1,
        evidence_items=[make_evidence()],
    )

    repo_2 = SqliteVerifiedClaimRepository(str(db_path))
    lookup = repo_2.get_by_claim_text("team a won the final 3-1")

    assert lookup is not None
    assert len(lookup.evidence_snapshot) == 1
    assert lookup.evidence_snapshot[0].evidence_text == "Team A won the final 3-1."
    assert lookup.metadata["evidence_snapshot_count"] == 1
