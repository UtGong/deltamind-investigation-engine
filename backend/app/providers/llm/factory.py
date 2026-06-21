from app.core.config import get_settings
from app.providers.llm.base import LLMProvider
from app.providers.llm.cached_provider import CachedLLMProvider
from app.providers.llm.dev_fallback_provider import DevFallbackLLMProvider
from app.providers.llm.gemini_provider import GeminiLLMProvider
from app.providers.llm.mock_provider import MockLLMProvider


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    provider_name = settings.llm_provider.lower().strip()

    if provider_name == "gemini":
        provider: LLMProvider = GeminiLLMProvider()
    elif provider_name == "mock":
        provider = MockLLMProvider()
    else:
        raise ValueError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")

    if settings.llm_cache_enabled and provider_name != "mock":
        provider = CachedLLMProvider(provider)

    if (
        settings.dev_llm_fallback_enabled
        and settings.app_env.lower().strip() in {"local", "dev", "development"}
        and provider_name != "mock"
    ):
        provider = DevFallbackLLMProvider(provider)

    return provider
