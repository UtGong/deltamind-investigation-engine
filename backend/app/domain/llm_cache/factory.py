from app.core.config import get_settings
from app.domain.llm_cache.base import LLMCacheRepository
from app.domain.llm_cache.postgres_repository import PostgresLLMCacheRepository
from app.domain.llm_cache.sqlite_repository import SQLiteLLMCacheRepository


def get_llm_cache_repository() -> LLMCacheRepository:
    settings = get_settings()
    backend = settings.database_backend.lower().strip()

    if backend == "postgres":
        return PostgresLLMCacheRepository()

    if backend == "sqlite":
        return SQLiteLLMCacheRepository(settings.llm_cache_db_path)

    raise ValueError(f"Unsupported DATABASE_BACKEND for LLM cache: {settings.database_backend}")
