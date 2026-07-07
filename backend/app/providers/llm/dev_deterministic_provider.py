from app.providers.llm.mock_provider import MockLLMProvider
from app.schemas.llm import LLMRequest, LLMResponse


class DevDeterministicLLMProvider(MockLLMProvider):
    """Generic deterministic local fallback for development.

    This provider intentionally contains no domain-specific facts. It exists only
    to keep local plumbing testable when a configured provider is unavailable.
    """

    name = "dev_deterministic_llm_provider"
    model = "generic-dev-deterministic-v1"

    def generate(self, request: LLMRequest) -> LLMResponse:
        response = super().generate(request)
        return response.model_copy(
            update={
                "provider": self.name,
                "model": self.model,
                "metadata": {**response.metadata, "generic_dev_fallback": True},
            }
        )
