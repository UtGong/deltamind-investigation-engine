from fastapi import APIRouter

from app.domain.cases.service import case_service
from app.schemas.api import CaseResponse, CreateCaseRequest

router = APIRouter(prefix="/cases", tags=["cases"])


@router.post("", response_model=CaseResponse)
def create_case(request: CreateCaseRequest) -> CaseResponse:
    return case_service.create_case(request)


@router.get("", response_model=list[CaseResponse])
def list_cases() -> list[CaseResponse]:
    return case_service.list_cases()


@router.get("/{case_id}", response_model=CaseResponse)
def get_case(case_id: str) -> CaseResponse:
    return case_service.get_case(case_id)
