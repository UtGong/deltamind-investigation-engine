from fastapi import APIRouter

from app.domain.verified_claims.models import VerifiedClaimRecord
from app.domain.verified_claims.service import verified_claim_service

router = APIRouter(prefix="/verified-claims", tags=["verified-claims"])


@router.get("", response_model=list[VerifiedClaimRecord])
def list_verified_claims() -> list[VerifiedClaimRecord]:
    return verified_claim_service.list_records()


@router.delete("")
def clear_verified_claims() -> dict:
    verified_claim_service.clear()
    return {"cleared": True}
