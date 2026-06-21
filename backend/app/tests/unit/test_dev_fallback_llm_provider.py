from app.providers.llm.base import LLMProvider
from app.providers.llm.dev_fallback_provider import DevFallbackLLMProvider
from app.providers.llm.dev_deterministic_provider import DevDeterministicLLMProvider
from app.schemas.llm import LLMMessage, LLMRequest


class FailingLLMProvider(LLMProvider):
    name = "failing_llm_provider"

    def generate(self, request: LLMRequest):
        raise RuntimeError("simulated upstream outage")


def test_dev_fallback_llm_provider_returns_mock_response_after_primary_failure():
    provider = DevFallbackLLMProvider(
        primary_provider=FailingLLMProvider(),
        fallback_provider=DevDeterministicLLMProvider(),
    )

    response = provider.generate(
        LLMRequest(
            messages=[
                LLMMessage(
                    role="user",
                    content="Create a retrieval plan for this claim: The Boston Celtics won the 2024 NBA Finals.",
                )
            ],
            temperature=0.0,
            response_format="json",
        )
    )

    assert response.content
    assert "after_failing_llm_provider_failure" in response.provider
