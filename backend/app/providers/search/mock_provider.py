from urllib.parse import quote_plus

from app.core.constants import SourceType
from app.schemas.search import SearchQuery, SearchResult


class MockSearchProvider:
    name = "mock_search_provider"

    def search(self, query: SearchQuery) -> list[SearchResult]:
        is_official = "official" in query.query.lower()

        source_type = SourceType.OFFICIAL if is_official else SourceType.MEDIA
        reliability = 0.92 if is_official else 0.70
        source_name = "Mock Official Source" if is_official else "Mock Media Source"
        domain = "official.example.com" if is_official else "media.example.com"

        return [
            SearchResult(
                result_id=f"{query.query_id}_result_1",
                query_id=query.query_id,
                title=f"{source_name}: Result for {query.query}",
                url=f"https://{domain}/search?q={quote_plus(query.query)}",
                snippet=f"Mock search result related to: {query.query}",
                source_name=source_name,
                domain=domain,
                source_type=source_type,
                reliability=reliability,
                independence=0.90 if is_official else 0.65,
                freshness=0.90,
                specificity=0.85,
            )
        ]
