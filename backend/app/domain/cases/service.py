from uuid import uuid4

from fastapi import HTTPException, status

from app.core.constants import CaseStatus
from app.domain.cases.models import CaseRecord
from app.domain.cases.repository import CaseRepository, case_repository
from app.schemas.api import CaseResponse, CreateCaseRequest


class CaseService:
    def __init__(self, repository: CaseRepository) -> None:
        self.repository = repository

    def create_case(self, request: CreateCaseRequest) -> CaseResponse:
        case = CaseRecord(
            case_id=f"case_{uuid4().hex}",
            title=request.title or self._make_title(request.input_text),
            input_type=request.input_type,
            input_text=request.input_text,
            status=CaseStatus.CREATED,
        )

        saved_case = self.repository.create(case)
        return self._to_response(saved_case)

    def get_case(self, case_id: str) -> CaseResponse:
        case = self.repository.get(case_id)

        if case is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Case not found: {case_id}",
            )

        return self._to_response(case)

    def list_cases(self) -> list[CaseResponse]:
        return [self._to_response(case) for case in self.repository.list()]

    def _to_response(self, case: CaseRecord) -> CaseResponse:
        return CaseResponse(
            case_id=case.case_id,
            title=case.title,
            input_type=case.input_type,
            input_text=case.input_text,
            status=case.status,
        )

    def _make_title(self, input_text: str) -> str:
        clean_text = " ".join(input_text.strip().split())
        if len(clean_text) <= 80:
            return clean_text
        return f"{clean_text[:77]}..."


case_service = CaseService(case_repository)
