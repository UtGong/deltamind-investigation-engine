from app.providers.llm.factory import get_llm_provider
from app.providers.llm.mock_provider import MockLLMProvider


def test_llm_provider_factory_uses_mock_in_tests():
    provider = get_llm_provider()

    assert isinstance(provider, MockLLMProvider)
