from app.core.constants import CaseStatus, ClaimType, InputType, StanceLabel, VerdictLabel
from app.db.models import (
    CaseRecord as DBCaseRecord,
    EvidenceRecord,
    SourceRecord,
    StanceRecord,
)
from app.db.session import SessionLocal, check_database_connection
from app.domain.cases.models import CaseRecord, utc_now
from app.domain.cases.postgres_repository import PostgresCaseRepository
from app.domain.investigations.postgres_repository import (
    PostgresInvestigationRepository,
)
from app.schemas.agent import AtomicClaim, EvidenceItem, PivotVerdict, StanceResult
from app.schemas.api import InvestigationResult


def test_postgres_investigation_materialization_dedupes_sources():
    health = check_database_connection()

    if not health["connected"]:
        return

    case_id = "case_postgres_duplicate_sources_test"
    case_repo = PostgresCaseRepository()
    investigation_repo = PostgresInvestigationRepository()

    with SessionLocal() as session:
        existing = session.get(DBCaseRecord, case_id)
        if existing is not None:
            session.delete(existing)
            session.commit()

    now = utc_now()

    case_repo.create(
        CaseRecord(
            case_id=case_id,
            input_type=InputType.CLAIM,
            input_text="The Boston Celtics won the 2024 NBA Finals.",
            title="Duplicate source materialization test",
            status=CaseStatus.CREATED,
            created_at=now,
            updated_at=now,
        )
    )

    claim = AtomicClaim(
        claim_id="claim_duplicate_sources_test",
        claim_text="The Boston Celtics won the 2024 NBA Finals.",
        claim_type=ClaimType.RESULT,
        confidence=0.95,
    )

    evidence_1 = EvidenceItem(
        evidence_id="evidence_duplicate_source_1",
        claim_id=claim.claim_id,
        source_id="source_nba_com",
        url="https://www.nba.com/search?query=Boston+Celtics",
        title="NBA Search",
        evidence_text="The Boston Celtics won the 2024 NBA Finals.",
        reliability=0.9,
        specificity=0.9,
    )

    evidence_2 = EvidenceItem(
        evidence_id="evidence_duplicate_source_2",
        claim_id=claim.claim_id,
        source_id="source_nba_com",
        url="https://www.nba.com/search?search=Boston+Celtics",
        title="NBA Search",
        evidence_text="Boston won the 2024 NBA Finals.",
        reliability=0.95,
        specificity=0.85,
    )

    stance_1 = StanceResult(
        claim_id=claim.claim_id,
        evidence_id=evidence_1.evidence_id,
        stance=StanceLabel.SUPPORTS,
        confidence=0.9,
        reason="Supports the claim.",
    )

    stance_2 = StanceResult(
        claim_id=claim.claim_id,
        evidence_id=evidence_2.evidence_id,
        stance=StanceLabel.SUPPORTS,
        confidence=0.88,
        reason="Also supports the claim.",
    )

    verdict = PivotVerdict(
        claim_id=claim.claim_id,
        verdict=VerdictLabel.SUPPORTED,
        confidence=0.9,
        support_score=0.9,
        contradiction_score=0.0,
        uncertainty_score=0.1,
        reason="Supported by duplicate-source evidence.",
    )

    result = InvestigationResult(
        case_id=case_id,
        status=CaseStatus.COMPLETED,
        case_verdict=VerdictLabel.SUPPORTED,
        confidence=0.9,
        claims=[claim],
        evidence=[evidence_1, evidence_2],
        stances=[stance_1, stance_2],
        verdicts=[verdict],
        report=None,
        agent_runs=[],
        cost_logs=[],
    )

    investigation_repo.save(result)

    with SessionLocal() as session:
        sources = (
            session.query(SourceRecord)
            .filter(SourceRecord.source_id == "source_nba_com")
            .all()
        )
        evidence_rows = (
            session.query(EvidenceRecord)
            .filter(EvidenceRecord.case_id == case_id)
            .all()
        )
        stance_rows = (
            session.query(StanceRecord)
            .filter(StanceRecord.case_id == case_id)
            .all()
        )

        assert len(sources) == 1
        assert len(evidence_rows) == 2
        assert len(stance_rows) == 2
        assert sources[0].reliability_prior == 0.95
