from urllib.parse import urlparse

from app.core.config import get_settings
from app.core.constants import SourceType
from app.schemas.search import SearchQuery, SearchResult


class DuckDuckGoSearchProvider:
    name = "duckduckgo_search_provider"

    def __init__(self, client=None, max_results: int | None = None) -> None:
        settings = get_settings()
        self.max_results = max_results or settings.tavily_max_results

        if client is not None:
            self.client = client
            return

        try:
            from duckduckgo_search import DDGS
        except ImportError as error:
            raise RuntimeError(
                "duckduckgo-search is not installed. Run: pip install duckduckgo-search"
            ) from error

        self.client = DDGS()

    def search(self, query: SearchQuery) -> list[SearchResult]:
        raw_items = self._search_with_fallbacks(query)

        results: list[SearchResult] = []

        for index, item in enumerate(raw_items, start=1):
            url = item.get("href") or item.get("url") or ""
            domain = self._extract_domain(url)

            if not url:
                continue

            results.append(
                SearchResult(
                    result_id=f"{query.query_id}_duckduckgo_result_{index}",
                    query_id=query.query_id,
                    title=item.get("title") or "Untitled search result",
                    url=url,
                    snippet=item.get("body") or item.get("snippet") or "",
                    source_name=domain,
                    domain=domain,
                    source_type=SourceType.UNKNOWN,
                    reliability=0.5,
                    independence=0.5,
                    freshness=0.5,
                    specificity=0.6,
                )
            )

        return results

    def _search_with_fallbacks(self, query: SearchQuery) -> list[dict]:
        search_texts = self._build_search_texts(query)

        collected: list[dict] = []
        seen_urls: set[str] = set()

        for search_text in search_texts:
            try:
                raw_results = list(
                    self.client.text(
                        search_text,
                        max_results=self.max_results,
                    )
                )
            except Exception:
                raw_results = []

            for item in raw_results:
                if not isinstance(item, dict):
                    continue

                url = item.get("href") or item.get("url") or ""
                if not url or url in seen_urls:
                    continue

                seen_urls.add(url)
                collected.append(item)

                if len(collected) >= self.max_results:
                    return collected

        return collected

    def _build_search_texts(self, query: SearchQuery) -> list[str]:
        texts: list[str] = []

        # Domain-targeted searches first.
        for domain in query.target_domains:
            cleaned_domain = domain.strip().lower()
            if cleaned_domain:
                texts.append(f"site:{cleaned_domain} {query.query}")

        # Plain query fallback. This is important because DDG often returns
        # nothing for strict site filters.
        texts.append(query.query)

        # Broader source-intent fallback.
        if query.expected_source_type != SourceType.UNKNOWN:
            texts.append(f"{query.query} {query.expected_source_type.value} source")

        # Deduplicate while preserving order.
        deduped: list[str] = []
        seen: set[str] = set()

        for text in texts:
            normalized = text.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                deduped.append(normalized)

        return deduped

    def _extract_domain(self, url: str) -> str:
        if not url:
            return "unknown"

        parsed = urlparse(url)
        return parsed.netloc.lower().removeprefix("www.") or "unknown"
