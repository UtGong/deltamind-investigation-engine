from app.core.constants import SourceType
from app.providers.search.duckduckgo_provider import DuckDuckGoSearchProvider
from app.schemas.search import SearchQuery


class FakeDDGSClient:
    def __init__(self):
        self.calls = []

    def text(self, query, max_results):
        self.calls.append(query)
        assert max_results == 2

        return [
            {
                "title": "Boston Celtics win 2024 NBA Finals",
                "href": "https://www.nba.com/news/boston-celtics-win-2024-nba-finals",
                "body": "The Celtics defeated the Mavericks to win the 2024 NBA Finals.",
            }
        ]


class EmptyThenResultDDGSClient:
    def __init__(self):
        self.calls = []

    def text(self, query, max_results):
        self.calls.append(query)

        if query.startswith("site:nba.com"):
            return []

        return [
            {
                "title": "Boston Celtics win 2024 NBA Finals",
                "href": "https://www.nba.com/news/boston-celtics-win-2024-nba-finals",
                "body": "The Celtics defeated the Mavericks to win the 2024 NBA Finals.",
            }
        ]


def make_query() -> SearchQuery:
    return SearchQuery(
        query_id="query_1",
        claim_id="claim_1",
        query="Boston Celtics won 2024 NBA Finals",
        purpose="Find official confirmation.",
        cost_tier="free",
        expected_source_type=SourceType.OFFICIAL,
        target_domains=["nba.com"],
        provider="duckduckgo",
    )


def test_duckduckgo_search_provider_returns_search_results():
    fake_client = FakeDDGSClient()

    provider = DuckDuckGoSearchProvider(
        client=fake_client,
        max_results=2,
    )

    results = provider.search(make_query())

    assert len(results) == 1
    assert results[0].query_id == "query_1"
    assert results[0].domain == "nba.com"
    assert results[0].source_type == SourceType.UNKNOWN
    assert "Celtics" in results[0].snippet
    assert fake_client.calls[0].startswith("site:nba.com")


def test_duckduckgo_search_provider_falls_back_to_plain_query():
    fake_client = EmptyThenResultDDGSClient()

    provider = DuckDuckGoSearchProvider(
        client=fake_client,
        max_results=2,
    )

    results = provider.search(make_query())

    assert len(results) == 1
    assert len(fake_client.calls) >= 2
    assert fake_client.calls[0].startswith("site:nba.com")
    assert fake_client.calls[1] == "Boston Celtics won 2024 NBA Finals"
