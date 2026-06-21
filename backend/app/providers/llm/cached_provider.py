import hashlib
import json
from typing import Any

from app.domain.llm_cache.base import LLMCacheRepository
from app.domain.llm_cache.sqlite_repository import SQLiteLLMCacheRepository
from app.providers.llm.base import LLMProvider
from app.schemas.llm import LLMRequest, LLMResponse


class CachedLLMProvider(LLMProvider):
    name = "cached_llm_provider"

    def __init__(
        self,
        wrapped_provider: LLMProvider,
        repository: LLMCacheRepository | None = None,
        db_path: str | None = None,
        cache_namespace: str | None = None,
    ) -> None:
        self.wrapped_provider = wrapped_provider
        self.cache_namespace = cache_namespace or wrapped_provider.name

        # Backward-compatible path for existing tests.
        self.repository = repository or SQLiteLLMCacheRepository(
            db_path or ":memory:"
        )

    def generate(self, request: LLMRequest) -> LLMResponse:
        request_hash = self._hash_request(request)
        cached = self.repository.get(request_hash)

        if cached is not None:
            self.repository.record_hit(request_hash)

            metadata = self._merge_metadata(
                cached.metadata,
                {
                    "cache_hit": True,
                    "llm_request_hash": request_hash,
                    "cache_namespace": cached.cache_namespace,
                    "cached_provider": cached.provider_name,
                    "original_input_tokens": cached.input_tokens,
                    "original_output_tokens": cached.output_tokens,
                    "original_estimated_cost_usd": cached.estimated_cost_usd,
                    "hit_count": cached.hit_count + 1,
                },
            )

            return LLMResponse(
                content=cached.content,
                provider=cached.provider_name,
                model=cached.model,
                input_tokens=0,
                output_tokens=0,
                estimated_cost_usd=0.0,
                metadata=metadata,
            )

        response = self.wrapped_provider.generate(request)

        self.repository.save(
            request_hash=request_hash,
            cache_namespace=self.cache_namespace,
            provider_name=response.provider,
            model=response.model,
            content=response.content,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            estimated_cost_usd=response.estimated_cost_usd,
            metadata=response.metadata or {},
        )

        metadata = self._merge_metadata(
            response.metadata,
            {
                "cache_hit": False,
                "llm_request_hash": request_hash,
                "cache_namespace": self.cache_namespace,
            },
        )

        return response.model_copy(update={"metadata": metadata})

    def clear(self) -> None:
        self.repository.clear()

    def _hash_request(self, request: LLMRequest) -> str:
        payload = {
            "cache_namespace": self.cache_namespace,
            "request": request.model_dump(mode="json"),
        }

        serialized = json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _merge_metadata(
        self,
        base_metadata: dict[str, Any] | None,
        extra_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        metadata = dict(base_metadata or {})
        metadata.update(extra_metadata)
        return metadata
