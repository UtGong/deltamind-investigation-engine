from app.core.constants import SourceType
from app.providers.search.tavily_provider import TavilySearchProvider
from app.schemas.search import SearchQuery


class FakeTavilyClient:
    def search(self, query: str, **kwargs) -> dict:
        return {
            "query": query,
            "results": [
                {
                    "title": "NBA Official Result",
                    "url": "https://www.nba.com/game/example",
                    "content": "Official NBA result content.",
                    "score": 0.91,
                }
            ],
        }


def test_tavily_search_provider_maps_results_without_source_judgment():
    provider = TavilySearchProvider(client=FakeTavilyClient())

    query = SearchQuery(
        query_id="query_1",
        claim_id="claim_1",
        query="Team A won the final official result",
        purpose="Find official result.",
    )

    results = provider.search(query)

    assert len(results) == 1
    assert results[0].result_id == "query_1_tavily_result_1"
    assert results[0].domain == "nba.com"

    # Provider retrieves. It should not decide authority.
    assert results[0].source_type == SourceType.UNKNOWN
    assert results[0].reliability == 0.5
