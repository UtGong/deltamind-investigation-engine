from app.core.constants import CaseStatus, InputType, VerdictLabel
from app.db.session import check_database_connection
from app.domain.cases.models import CaseRecord, utc_now
from app.domain.cases.postgres_repository import PostgresCaseRepository
from app.domain.investigations.postgres_repository import (
    PostgresInvestigationRepository,
)
from app.schemas.api import InvestigationResult


def test_postgres_case_and_investigation_repository_roundtrip_when_database_connected():
    health = check_database_connection()

    if not health["connected"]:
        return

    case_repo = PostgresCaseRepository()
    investigation_repo = PostgresInvestigationRepository()

    case_id = "case_postgres_case_repo_test"

    # Clean previous run if it exists.
    from app.db.models import CaseRecord as DBCaseRecord
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        existing = session.get(DBCaseRecord, case_id)
        if existing is not None:
            session.delete(existing)
            session.commit()

    now = utc_now()

    case = CaseRecord(
        case_id=case_id,
        input_type=InputType.CLAIM,
        input_text="The Boston Celtics won the 2024 NBA Finals.",
        title="Postgres case test",
        status=CaseStatus.CREATED,
        created_at=now,
        updated_at=now,
    )

    created = case_repo.create(case)
    assert created.case_id == case_id

    loaded = case_repo.get(case_id)
    assert loaded is not None
    assert loaded.case_id == case_id
    assert loaded.input_text == case.input_text
    assert loaded.status == CaseStatus.CREATED

    updated = loaded.model_copy(update={"status": CaseStatus.RUNNING})
    case_repo.update(updated)

    loaded_after_update = case_repo.get(case_id)
    assert loaded_after_update is not None
    assert loaded_after_update.status == CaseStatus.RUNNING

    result = InvestigationResult(
        case_id=case_id,
        status=CaseStatus.COMPLETED,
        case_verdict=VerdictLabel.SUPPORTED,
        confidence=0.91,
        claims=[],
        evidence=[],
        stances=[],
        verdicts=[],
        report=None,
        agent_runs=[],
        cost_logs=[],
    )

    saved_result = investigation_repo.save(result)
    assert saved_result.case_id == case_id

    loaded_result = investigation_repo.get(case_id)
    assert loaded_result is not None
    assert loaded_result.case_id == case_id
    assert loaded_result.status == CaseStatus.COMPLETED
    assert loaded_result.case_verdict == VerdictLabel.SUPPORTED
    assert loaded_result.confidence == 0.91

    loaded_case_after_result = case_repo.get(case_id)
    assert loaded_case_after_result is not None
    assert loaded_case_after_result.status == CaseStatus.COMPLETED
