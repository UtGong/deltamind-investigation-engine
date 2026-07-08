from functools import lru_cache

from pydantic import model_validator
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
    database_url: str = ""
    embedding_dimension: int = 768

    # LLM
    llm_provider: str = "ollama"
    dev_llm_fallback_enabled: bool = False
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    ollama_timeout_seconds: int = 60

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

    @model_validator(mode="after")
    def normalize_database_settings(self) -> "Settings":
        backend = (self.database_backend or "").strip().lower()
        self.database_backend = backend or "sqlite"

        if backend == "sqlite":
            candidate = (self.database_url or "").strip()
            if not candidate:
                self.database_url = "sqlite:///./data/deltamind_local.sqlite3"
            else:
                self.database_url = candidate
        else:
            self.database_url = (self.database_url or "").strip()

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
