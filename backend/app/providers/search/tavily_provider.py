from urllib.parse import urlparse

from tavily import TavilyClient

from app.core.config import get_settings
from app.core.constants import SourceType
from app.schemas.search import SearchQuery, SearchResult


class TavilySearchProvider:
    name = "tavily_search_provider"

    def __init__(self, client: TavilyClient | None = None) -> None:
        settings = get_settings()

        if client is not None:
            self.client = client
            self.max_results = settings.tavily_max_results
            self.search_depth = settings.tavily_search_depth
            return

        if not settings.tavily_api_key:
            raise ValueError(
                "TAVILY_API_KEY is missing. Set it in backend/.env or environment variables."
            )

        self.client = TavilyClient(api_key=settings.tavily_api_key)
        self.max_results = settings.tavily_max_results
        self.search_depth = settings.tavily_search_depth

    def search(self, query: SearchQuery) -> list[SearchResult]:
        response = self.client.search(
            query.query,
            max_results=self.max_results,
            search_depth=self.search_depth,
            include_answer=False,
            include_raw_content=False,
        )

        raw_results = response.get("results", [])
        results: list[SearchResult] = []

        for index, item in enumerate(raw_results, start=1):
            url = item.get("url") or ""
            domain = self._extract_domain(url)

            results.append(
                SearchResult(
                    result_id=f"{query.query_id}_tavily_result_{index}",
                    query_id=query.query_id,
                    title=item.get("title") or "Untitled Tavily Result",
                    url=url,
                    snippet=item.get("content") or item.get("snippet") or "",
                    source_name=domain,
                    domain=domain,
                    source_type=SourceType.UNKNOWN,
                    reliability=0.5,
                    independence=0.5,
                    freshness=0.5,
                    specificity=self._specificity_from_search_score(item),
                )
            )

        return results

    def _extract_domain(self, url: str) -> str:
        if not url:
            return "unknown"

        parsed = urlparse(url)
        return parsed.netloc.lower().removeprefix("www.") or "unknown"

    def _specificity_from_search_score(self, item: dict) -> float:
        score = item.get("score")

        if isinstance(score, int | float):
            return max(0.3, min(0.95, float(score)))

        return 0.5
