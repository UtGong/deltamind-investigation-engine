from app.core.config import get_settings
from app.domain.llm_cache.factory import get_llm_cache_repository
from app.providers.llm.base import LLMProvider
from app.providers.llm.cached_provider import CachedLLMProvider
from app.providers.llm.gemini_provider import GeminiLLMProvider
from app.providers.llm.mock_provider import MockLLMProvider


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    provider_name = settings.llm_provider.lower().strip()

    if provider_name == "mock":
        return MockLLMProvider()

    if provider_name == "gemini":
        provider: LLMProvider = GeminiLLMProvider()

        if settings.llm_cache_enabled:
            provider = CachedLLMProvider(
                wrapped_provider=provider,
                repository=get_llm_cache_repository(),
                cache_namespace=f"gemini::{settings.gemini_model}",
            )

        return provider

    raise ValueError(f"Unsupported LLM provider: {settings.llm_provider}")
