from fastapi import APIRouter

from app.db.session import check_database_connection

router = APIRouter(prefix="/database", tags=["database"])


@router.get("/health")
def get_database_health() -> dict:
    return check_database_connection()
