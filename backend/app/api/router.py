from fastapi import APIRouter

from app.api.routes import (
    audit,
    cases,
    database,
    investigations,
    llm_cache,
    system,
    verified_claims,
)

api_router = APIRouter()
api_router.include_router(cases.router)
api_router.include_router(investigations.router)
api_router.include_router(audit.router)
api_router.include_router(system.router)
api_router.include_router(database.router)
api_router.include_router(llm_cache.router)
api_router.include_router(verified_claims.router)
