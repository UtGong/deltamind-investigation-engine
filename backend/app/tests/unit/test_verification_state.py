import pytest
from fastapi import HTTPException

from app.core.constants import InputType
from app.domain.audit.repository import InMemoryAuditRepository
from app.domain.audit.service import AuditService
from app.domain.cases.models import CaseRecord
from app.domain.cases.repository import InMemoryCaseRepository
from app.domain.investigations.repository import InMemoryInvestigationRepository
from app.domain.investigations.service import InvestigationService
from app.domain.verified_claims.repository import InMemoryVerifiedClaimRepository
from app.domain.verified_claims.service import VerifiedClaimService


def make_service() -> tuple[InvestigationService, InMemoryCaseRepository]:
    case_repo = InMemoryCaseRepository()
    audit = AuditService(InMemoryAuditRepository())
    service = InvestigationService(
        case_repo=case_repo,
        investigation_repo=InMemoryInvestigationRepository(),
        audit=audit,
        verified_claims=VerifiedClaimService(InMemoryVerifiedClaimRepository()),
    )
    return service, case_repo


def test_verification_state_for_created_case_returns_not_ready_fields():
    service, case_repo = make_service()
    case = case_repo.create(
        CaseRecord(
            case_id="case_test",
            input_type=InputType.CLAIM,
            input_text="Example organization announced a verified milestone.",
            title="Test claim",
        )
    )

    state = service.get_verification_state(case.case_id)

    assert state.case_id == case.case_id
    assert state.case_available is True
    assert state.case_status == "queued"
    assert state.investigation_available is False
    assert state.certificate_available is False
    assert state.evidence_graph_available is False
    assert state.error_available is False
    assert state.investigation is None
    assert state.trust_certificate is None
    assert state.evidence_graph is None
    assert state.error is None


def test_verification_state_surfaces_recorded_failure():
    service, case_repo = make_service()
    case = case_repo.create(
        CaseRecord(
            case_id="case_failed",
            input_type=InputType.CLAIM,
            input_text="Example organization announced a verified milestone.",
        )
    )

    service.mark_case_failed(
        case_id=case.case_id,
        stage="unit_test_stage",
        agent_name="unit_test_agent",
        error=RuntimeError("boom"),
    )

    state = service.get_verification_state(case.case_id)

    assert state.case_status == "failed"
    assert state.error_available is True
    assert state.error is not None
    assert state.error.stage == "unit_test_stage"
    assert state.error.agent_name == "unit_test_agent"
    assert state.error.error_type == "RuntimeError"
    assert state.error.error_message == "boom"


def test_verification_state_missing_case_raises_404():
    service, _case_repo = make_service()

    with pytest.raises(HTTPException) as exc_info:
        service.get_verification_state("case_missing")

    assert exc_info.value.status_code == 404
