from fastapi import APIRouter, HTTPException, status

from app.domain.investigations.service import investigation_service
from app.domain.trust_certificates.registry import trust_certificate_registry

router = APIRouter(prefix="/cases", tags=["investigations"])


@router.post("/{case_id}/investigate")
def investigate_case(case_id: str):
    try:
        return investigation_service.investigate_case(case_id)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "Investigation failed due to an unhandled backend error.",
                "case_id": case_id,
                "error_type": type(error).__name__,
                "error_message": str(error),
            },
        ) from error


@router.get("/{case_id}/investigation")
def get_investigation_result(case_id: str):
    return investigation_service.get_result(case_id)


@router.get("/{case_id}/evidence-graph")
def get_evidence_graph(case_id: str):
    result = investigation_service.get_result(case_id)
    evidence_graph = result.evidence_graph

    if evidence_graph is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": "Evidence graph is not available for this case.",
                "case_id": case_id,
            },
        )

    return evidence_graph


@router.get("/{case_id}/trust-certificate")
def get_trust_certificate(case_id: str):
    result = investigation_service.get_result(case_id)
    trust_certificate = result.trust_certificate

    if trust_certificate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": "Trust certificate is not available for this case.",
                "case_id": case_id,
            },
        )

    return trust_certificate


@router.get("/trust-certificates")
def list_trust_certificates(limit: int = 20):
    return trust_certificate_registry.list_recent(limit=limit)


@router.get("/trust-certificates/recent")
def list_recent_trust_certificates(limit: int = 20):
    return trust_certificate_registry.list_recent(limit=limit)
