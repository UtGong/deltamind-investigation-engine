from app.core.config import get_settings
from app.providers.search.base import SearchProvider
from app.providers.search.duckduckgo_provider import DuckDuckGoSearchProvider
from app.providers.search.mock_provider import MockSearchProvider
from app.providers.search.no_search_provider import NoSearchProvider
from app.providers.search.tavily_provider import TavilySearchProvider


def _build_provider(provider: str) -> SearchProvider:
    normalized = provider.lower().strip()

    if normalized == "no_search":
        return NoSearchProvider()

    if normalized in {"duckduckgo", "ddg"}:
        return DuckDuckGoSearchProvider()

    if normalized == "tavily":
        return TavilySearchProvider()

    if normalized == "mock":
        return MockSearchProvider()

    raise ValueError(f"Unsupported search provider: {provider}")


def get_free_search_provider() -> SearchProvider:
    settings = get_settings()
    return _build_provider(settings.free_search_provider)


def get_paid_search_provider() -> SearchProvider:
    settings = get_settings()
    return _build_provider(settings.paid_search_provider)


def get_search_provider() -> SearchProvider:
    return get_free_search_provider()
