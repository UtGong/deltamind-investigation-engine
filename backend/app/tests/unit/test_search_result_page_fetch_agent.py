from app.agents.search_result_page_fetch_agent import (
    SearchResultPageFetchAgent,
    SearchResultPageFetchInput,
)
from app.agents.url_fetch_agent import UrlFetchOutput
from app.core.constants import ClaimType
from app.schemas.agent import AtomicClaim
from app.schemas.search import SearchResult


class FakeUrlFetchAgent:
    def run(self, input_data):
        return UrlFetchOutput(
            url=str(input_data.url),
            final_url=str(input_data.url),
            status_code=200,
            title="Fetched page title",
            text="Full fetched page text confirming Team A won the final 3-1.",
            error=None,
        )


class FailingUrlFetchAgent:
    def run(self, input_data):
        return UrlFetchOutput(
            url=str(input_data.url),
            final_url=None,
            status_code=None,
            title=None,
            text=None,
            error="fetch failed",
        )


def make_claim() -> AtomicClaim:
    return AtomicClaim(
        claim_id="claim_1",
        claim_text="Team A won the final 3-1.",
        claim_type=ClaimType.RESULT,
        confidence=0.9,
    )


def make_search_result(snippet: str = "Short snippet.") -> SearchResult:
    return SearchResult(
        result_id="result_1",
        query_id="query_1",
        title="Search result title",
        url="https://example.com/source",
        snippet=snippet,
        source_name="example.com",
        domain="example.com",
        reliability=0.5,
        independence=0.5,
        freshness=0.5,
        specificity=0.6,
    )


def test_search_result_page_fetch_agent_enriches_short_snippet():
    agent = SearchResultPageFetchAgent(
        url_fetch_agent=FakeUrlFetchAgent(),
        max_page_chars=1000,
    )

    output = agent.run(
        SearchResultPageFetchInput(
            claim=make_claim(),
            search_results=[make_search_result()],
        )
    )

    assert output.fetched_count == 1
    assert output.skipped_count == 0
    assert output.failed_urls == []

    enriched = output.results[0]
    assert enriched.title == "Fetched page title"
    assert "Full fetched page text" in enriched.snippet


def test_search_result_page_fetch_agent_keeps_original_on_fetch_failure():
    agent = SearchResultPageFetchAgent(
        url_fetch_agent=FailingUrlFetchAgent(),
    )

    output = agent.run(
        SearchResultPageFetchInput(
            claim=make_claim(),
            search_results=[make_search_result()],
        )
    )

    assert output.fetched_count == 0
    assert output.failed_urls == ["https://example.com/source"]
    assert output.results[0].snippet == "Short snippet."


def test_search_result_page_fetch_agent_skips_long_existing_snippet():
    long_snippet = "x" * 2000

    agent = SearchResultPageFetchAgent(
        url_fetch_agent=FakeUrlFetchAgent(),
        min_existing_snippet_chars_to_skip=1800,
    )

    output = agent.run(
        SearchResultPageFetchInput(
            claim=make_claim(),
            search_results=[make_search_result(long_snippet)],
        )
    )

    assert output.fetched_count == 0
    assert output.skipped_count == 1
    assert output.results[0].snippet == long_snippet
