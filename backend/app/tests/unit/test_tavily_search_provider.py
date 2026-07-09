from app.core.constants import SourceType
from app.providers.search.tavily_provider import TavilySearchProvider
from app.schemas.search import SearchQuery


class FakeTavilyClient:
    def __init__(self) -> None:
        self.queries = []

    def search(self, query: str, **kwargs) -> dict:
        self.queries.append(query)
        return {
            "query": query,
            "results": [
                {
                    "title": "Official Result",
                    "url": "https://www.example.org/game/example",
                    "content": "Official official result content.",
                    "score": 0.91,
                }
            ],
        }


def test_tavily_search_provider_maps_results_without_source_judgment():
    client = FakeTavilyClient()
    provider = TavilySearchProvider(client=client)

    query = SearchQuery(
        query_id="query_1",
        claim_id="claim_1",
        query="Team A won the final official result",
        purpose="Find official result.",
    )

    results = provider.search(query)

    assert len(results) == 1
    assert results[0].result_id == "query_1_tavily_result_1"
    assert results[0].domain == "example.org"

    # Provider retrieves. It should not decide authority.
    assert results[0].source_type == SourceType.UNKNOWN
    assert results[0].reliability == 0.5


def test_tavily_search_provider_includes_target_domains_in_query_text():
    client = FakeTavilyClient()
    provider = TavilySearchProvider(client=client)

    query = SearchQuery(
        query_id="query_1",
        claim_id="claim_1",
        query="Belgium USA 2026 FIFA World Cup score 3-1",
        purpose="Find match result.",
        target_domains=["fifa.com", "espn.com"],
    )

    provider.search(query)

    assert "site:fifa.com" in client.queries[0]
    assert "site:espn.com" in client.queries[0]
    assert "Belgium USA 2026 FIFA World Cup score 3-1" in client.queries[0]
