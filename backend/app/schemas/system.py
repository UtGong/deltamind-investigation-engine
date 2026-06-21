from pydantic import BaseModel


class SystemStatusResponse(BaseModel):
    app_name: str
    app_version: str
    app_env: str

    database_backend: str
    database_url_configured: bool

    llm_provider: str
    gemini_model: str | None = None
    llm_cache_enabled: bool
    llm_cache_db_path: str

    search_planner_provider: str
    verified_claim_db_path: str

    free_search_provider: str
    paid_search_provider: str
    allow_paid_search: bool
    max_paid_search_calls_per_case: int

    tavily_max_results: int
    tavily_search_depth: str
