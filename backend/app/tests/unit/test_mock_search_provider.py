from app.core.constants import SourceType
from app.providers.search.mock_provider import MockSearchProvider
from app.schemas.search import SearchQuery


def test_mock_search_provider_returns_official_result():
    provider = MockSearchProvider()

    query = SearchQuery(
        query_id="query_1",
        claim_id="claim_1",
        query="Player X joined Club A official source",
        purpose="Find official source.",
    )

    results = provider.search(query)

    assert len(results) == 1
    assert results[0].source_type == SourceType.OFFICIAL
    assert results[0].reliability > 0.9


def test_mock_search_provider_returns_media_result():
    provider = MockSearchProvider()

    query = SearchQuery(
        query_id="query_1",
        claim_id="claim_1",
        query="Player X joined Club A independent report",
        purpose="Find independent report.",
    )

    results = provider.search(query)

    assert len(results) == 1
    assert results[0].source_type == SourceType.MEDIA
    assert results[0].reliability < 0.9
