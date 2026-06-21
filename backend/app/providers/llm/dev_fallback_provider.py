from app.providers.llm.base import LLMProvider
from app.providers.llm.mock_provider import MockLLMProvider
from app.schemas.llm import LLMRequest, LLMResponse


class DevFallbackLLMProvider(LLMProvider):
    """Development-only wrapper.

    It tries the primary provider first. If the primary provider fails, it falls
    back to MockLLMProvider so local pipeline testing can continue.

    This wrapper should only be enabled in local/dev environments.
    """

    name = "dev_fallback_llm_provider"

    def __init__(
        self,
        primary_provider: LLMProvider,
        fallback_provider: LLMProvider | None = None,
    ) -> None:
        self.primary_provider = primary_provider
        self.fallback_provider = fallback_provider or MockLLMProvider()

    def generate(self, request: LLMRequest) -> LLMResponse:
        try:
            return self.primary_provider.generate(request)
        except Exception as error:
            response = self.fallback_provider.generate(request)

            provider_name = getattr(response, "provider", None) or self.fallback_provider.name
            model_name = getattr(response, "model", None) or "mock-dev-fallback"

            return response.model_copy(
                update={
                    "provider": f"{provider_name}_after_{self.primary_provider.name}_failure",
                    "model": model_name,
                }
            )
