from app.core.constants import CaseStatus, ClaimType, InputType, StanceLabel, VerdictLabel
from app.db.models import (
    CaseRecord as DBCaseRecord,
    ClaimRecord,
    EvidenceRecord,
    SourceRecord,
    SourceReliabilityRecord,
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


def test_postgres_investigation_save_materializes_claim_evidence_and_stance():
    health = check_database_connection()

    if not health["connected"]:
        return

    case_repo = PostgresCaseRepository()
    investigation_repo = PostgresInvestigationRepository()

    case_id = "case_postgres_materialization_test"

    with SessionLocal() as session:
        existing = session.get(DBCaseRecord, case_id)
        if existing is not None:
            session.delete(existing)
        session.query(SourceReliabilityRecord).filter(
            SourceReliabilityRecord.domain.in_(["example.org", "www.example.org"])
        ).delete(synchronize_session=False)
        session.commit()

    now = utc_now()

    case_repo.create(
        CaseRecord(
            case_id=case_id,
            input_type=InputType.CLAIM,
            input_text="The Team Green won the 2024 Example Final.",
            title="Materialization test",
            status=CaseStatus.CREATED,
            created_at=now,
            updated_at=now,
        )
    )

    claim = AtomicClaim(
        claim_id="claim_materialization_test",
        claim_text="The Team Green won the 2024 Example Final.",
        claim_type=ClaimType.RESULT,
        subject="Team Green",
        predicate="won",
        object="2024 Example Final",
        confidence=0.95,
    )

    evidence = EvidenceItem(
        evidence_id="evidence_materialization_test",
        claim_id=claim.claim_id,
        source_id="source_materialization_test",
        url="https://www.example.org/news/celtics-win-2024-example-final",
        title="Team Green win 2024 Example Final",
        evidence_text="The Team Green defeated the Team Silver to win the 2024 Example Final.",
        reliability=0.9,
        independence=0.8,
        freshness=0.7,
        specificity=0.95,
    )

    stance = StanceResult(
        claim_id=claim.claim_id,
        evidence_id=evidence.evidence_id,
        stance=StanceLabel.SUPPORTS,
        confidence=0.92,
        reason="The evidence directly supports the claim.",
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

    result = InvestigationResult(
        case_id=case_id,
        status=CaseStatus.COMPLETED,
        case_verdict=VerdictLabel.SUPPORTED,
        confidence=0.91,
        claims=[claim],
        evidence=[evidence],
        stances=[stance],
        verdicts=[verdict],
        report=None,
        agent_runs=[],
        cost_logs=[],
    )

    investigation_repo.save(result)

    with SessionLocal() as session:
        db_case = session.get(DBCaseRecord, case_id)
        db_claim = session.get(ClaimRecord, claim.claim_id)
        db_source = session.get(SourceRecord, evidence.source_id)
        db_evidence = session.get(EvidenceRecord, evidence.evidence_id)
        db_source_reliability = (
            session.query(SourceReliabilityRecord)
            .filter(SourceReliabilityRecord.domain == "example.org")
            .filter(SourceReliabilityRecord.claim_type == ClaimType.RESULT.value)
            .filter(SourceReliabilityRecord.topic == "Team Green")
            .first()
        )

        db_stances = (
            session.query(StanceRecord)
            .filter(StanceRecord.case_id == case_id)
            .all()
        )

        assert db_case is not None
        assert db_case.status == CaseStatus.COMPLETED.value
        assert db_case.case_verdict == VerdictLabel.SUPPORTED.value
        assert db_case.confidence == 0.91
        assert db_case.investigation_result_json is not None

        assert db_claim is not None
        assert db_claim.case_id == case_id
        assert db_claim.claim_text == claim.claim_text
        assert db_claim.claim_type == ClaimType.RESULT.value
        assert db_claim.final_verdict == VerdictLabel.SUPPORTED.value
        assert db_claim.correctness_score == 0.91

        assert db_source is not None
        assert db_source.source_id == evidence.source_id
        assert db_source.domain == "www.example.org"
        assert db_source.reliability_prior is not None
        assert db_source.reliability_prior > 0.9

        assert db_source_reliability is not None
        assert db_source_reliability.num_observations == 1
        assert db_source_reliability.reliability_mean > 0.9

        assert db_evidence is not None
        assert db_evidence.case_id == case_id
        assert db_evidence.claim_id == claim.claim_id
        assert db_evidence.source_id == evidence.source_id
        assert db_evidence.reliability == 0.9
        assert db_evidence.specificity == 0.95

        assert len(db_stances) == 1
        assert db_stances[0].stance_label == StanceLabel.SUPPORTS.value
        assert db_stances[0].confidence == 0.92
