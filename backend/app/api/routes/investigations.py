from fastapi import APIRouter, HTTPException, status

from app.domain.investigations.service import investigation_service

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
