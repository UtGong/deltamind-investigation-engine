from fastapi import APIRouter

from app.core.config import get_settings
from app.providers.search.factory import get_free_search_provider
from app.schemas.system import SystemStatusResponse

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status", response_model=SystemStatusResponse)
def get_system_status() -> SystemStatusResponse:
    settings = get_settings()
    free_search_provider = get_free_search_provider()

    return SystemStatusResponse(
        app_name=settings.app_name,
        app_version=settings.app_version,
        app_env=settings.app_env,
        database_backend=settings.database_backend,
        database_url_configured=bool(settings.database_url),
        llm_provider=settings.llm_provider,
        gemini_model=settings.gemini_model,
        llm_cache_enabled=settings.llm_cache_enabled,
        dev_llm_fallback_enabled=settings.dev_llm_fallback_enabled,
        llm_cache_db_path=settings.llm_cache_db_path,
        search_planner_provider=settings.search_planner_provider,
        verified_claim_db_path=settings.verified_claim_db_path,
        free_search_provider=free_search_provider.name,
        paid_search_provider=settings.paid_search_provider,
        allow_paid_search=settings.allow_paid_search,
        max_paid_search_calls_per_case=settings.max_paid_search_calls_per_case,
        tavily_max_results=settings.tavily_max_results,
        tavily_search_depth=settings.tavily_search_depth,
    )
