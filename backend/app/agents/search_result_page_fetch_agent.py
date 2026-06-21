from pydantic import BaseModel, Field

from app.agents.base import Agent
from app.agents.url_fetch_agent import UrlFetchAgent, UrlFetchInput
from app.schemas.agent import AtomicClaim
from app.schemas.search import SearchResult


class SearchResultPageFetchInput(BaseModel):
    claim: AtomicClaim
    search_results: list[SearchResult]


class SearchResultPageFetchOutput(BaseModel):
    results: list[SearchResult] = Field(default_factory=list)
    fetched_count: int = 0
    skipped_count: int = 0
    failed_urls: list[str] = Field(default_factory=list)


class SearchResultPageFetchAgent(
    Agent[SearchResultPageFetchInput, SearchResultPageFetchOutput]
):
    name = "search_result_page_fetch_agent"

    def __init__(
        self,
        url_fetch_agent: UrlFetchAgent | None = None,
        max_page_chars: int = 6000,
        min_existing_snippet_chars_to_skip: int = 1800,
    ) -> None:
        self.url_fetch_agent = url_fetch_agent or UrlFetchAgent()
        self.max_page_chars = max_page_chars
        self.min_existing_snippet_chars_to_skip = min_existing_snippet_chars_to_skip

    def run(
        self,
        input_data: SearchResultPageFetchInput,
    ) -> SearchResultPageFetchOutput:
        enriched_results: list[SearchResult] = []
        fetched_count = 0
        skipped_count = 0
        failed_urls: list[str] = []

        for result in input_data.search_results:
            if not result.url:
                enriched_results.append(result)
                skipped_count += 1
                continue

            # Direct-source fetch results already contain page-level text.
            if len(result.snippet or "") >= self.min_existing_snippet_chars_to_skip:
                enriched_results.append(result)
                skipped_count += 1
                continue

            fetched = self.url_fetch_agent.run(
                UrlFetchInput(url=result.url)
            )

            if fetched.error or not fetched.text:
                enriched_results.append(result)
                failed_urls.append(result.url)
                continue

            enriched_results.append(
                result.model_copy(
                    update={
                        "title": fetched.title or result.title,
                        "url": fetched.final_url or result.url,
                        "snippet": fetched.text[: self.max_page_chars],
                    }
                )
            )
            fetched_count += 1

        return SearchResultPageFetchOutput(
            results=enriched_results,
            fetched_count=fetched_count,
            skipped_count=skipped_count,
            failed_urls=failed_urls,
        )
