from app.schemas.search import SearchQuery, SearchResult


class NoSearchProvider:
    name = "no_search_provider"

    def search(self, query: SearchQuery) -> list[SearchResult]:
        return []
