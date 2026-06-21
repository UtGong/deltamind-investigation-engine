from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DeltaMind Verify API"
    app_description: str = "Agent-based investigation engine for claim verification."
    app_version: str = "0.1.0"
    app_env: str = "local"

    api_prefix: str = "/api/v1"
    log_level: str = "INFO"

    # Database
    # sqlite = current local repositories / legacy cache path
    # postgres = PostgreSQL + pgvector operational store
    database_backend: str = "sqlite"
    database_url: str = "postgresql+psycopg://deltamind:deltamind_dev_password@localhost:5432/deltamind"
    embedding_dimension: int = 768

    # LLM
    llm_provider: str = "mock"
    dev_llm_fallback_enabled: bool = False
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"

    # Exact LLM request cache
    llm_cache_enabled: bool = True
    llm_cache_db_path: str = "data/llm_cache.sqlite3"

    # Planner policy
    # llm = run Gemini planner for every unverified claim
    # deterministic = emergency/test fallback only
    search_planner_provider: str = "llm"

    # Persistent verified-claim database
    verified_claim_db_path: str = "data/verified_claims.sqlite3"

    # Search policy
    free_search_provider: str = "no_search"
    paid_search_provider: str = "tavily"
    allow_paid_search: bool = False
    max_paid_search_calls_per_case: int = 0

    # Tavily cost controls
    tavily_api_key: str | None = None
    tavily_max_results: int = 3
    tavily_search_depth: str = "basic"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
