from abc import ABC, abstractmethod

from app.schemas.search import SearchQuery, SearchResult


class SearchProvider(ABC):
    name: str

    @abstractmethod
    def search(self, query: SearchQuery) -> list[SearchResult]:
        raise NotImplementedError
