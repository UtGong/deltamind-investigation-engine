from dataclasses import dataclass
from typing import Protocol


@dataclass
class CachedLLMEntry:
    request_hash: str
    cache_namespace: str
    provider_name: str
    model: str | None
    content: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    metadata: dict
    hit_count: int


class LLMCacheRepository(Protocol):
    def get(self, request_hash: str) -> CachedLLMEntry | None:
        ...

    def save(
        self,
        request_hash: str,
        cache_namespace: str,
        provider_name: str,
        model: str | None,
        content: str,
        input_tokens: int,
        output_tokens: int,
        estimated_cost_usd: float,
        metadata: dict,
    ) -> None:
        ...

    def record_hit(self, request_hash: str) -> None:
        ...

    def clear(self) -> None:
        ...

    def stats(self) -> dict:
        ...
