from app.providers.llm.base import LLMProvider
from app.providers.llm.cached_provider import CachedLLMProvider
from app.schemas.llm import LLMMessage, LLMRequest, LLMResponse


class CountingLLMProvider(LLMProvider):
    name = "counting_llm_provider"

    def __init__(self) -> None:
        self.call_count = 0

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.call_count += 1

        return LLMResponse(
            content='{"ok": true}',
            provider=self.name,
            model="counting-model",
            input_tokens=10,
            output_tokens=5,
            estimated_cost_usd=0.01,
            metadata={"call_count": self.call_count},
        )


def make_request(content: str = "hello") -> LLMRequest:
    return LLMRequest(
        messages=[
            LLMMessage(
                role="user",
                content=content,
            )
        ],
        temperature=0.0,
        response_format="json",
    )


def test_cached_llm_provider_reuses_exact_same_request(tmp_path):
    wrapped = CountingLLMProvider()
    provider = CachedLLMProvider(
        wrapped_provider=wrapped,
        db_path=str(tmp_path / "llm_cache.sqlite3"),
        cache_namespace="test-model",
    )

    first = provider.generate(make_request())
    second = provider.generate(make_request())

    assert wrapped.call_count == 1

    assert first.content == second.content
    assert first.metadata["cache_hit"] is False
    assert second.metadata["cache_hit"] is True

    assert first.input_tokens == 10
    assert first.output_tokens == 5

    assert second.input_tokens == 0
    assert second.output_tokens == 0
    assert second.estimated_cost_usd == 0.0


def test_cached_llm_provider_does_not_reuse_different_request(tmp_path):
    wrapped = CountingLLMProvider()
    provider = CachedLLMProvider(
        wrapped_provider=wrapped,
        db_path=str(tmp_path / "llm_cache.sqlite3"),
        cache_namespace="test-model",
    )

    provider.generate(make_request("hello"))
    provider.generate(make_request("different"))

    assert wrapped.call_count == 2


def test_cached_llm_provider_namespace_separates_cache(tmp_path):
    db_path = tmp_path / "llm_cache.sqlite3"

    wrapped_1 = CountingLLMProvider()
    provider_1 = CachedLLMProvider(
        wrapped_provider=wrapped_1,
        db_path=str(db_path),
        cache_namespace="model-a",
    )

    wrapped_2 = CountingLLMProvider()
    provider_2 = CachedLLMProvider(
        wrapped_provider=wrapped_2,
        db_path=str(db_path),
        cache_namespace="model-b",
    )

    provider_1.generate(make_request())
    provider_2.generate(make_request())

    assert wrapped_1.call_count == 1
    assert wrapped_2.call_count == 1
