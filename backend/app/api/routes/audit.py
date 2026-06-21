from fastapi import APIRouter

from app.domain.audit.service import audit_service
from app.schemas.api import AuditTrailResponse

router = APIRouter(prefix="/cases", tags=["audit"])


@router.get("/{case_id}/audit", response_model=AuditTrailResponse)
def get_case_audit(case_id: str) -> AuditTrailResponse:
    audit_trail = audit_service.get_trail(case_id)
    return AuditTrailResponse.model_validate(audit_trail.model_dump())
