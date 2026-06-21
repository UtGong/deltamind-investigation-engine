import json

from app.providers.llm.dev_deterministic_provider import DevDeterministicLLMProvider
from app.schemas.llm import LLMMessage, LLMRequest


def test_dev_deterministic_provider_returns_search_plan():
    provider = DevDeterministicLLMProvider()

    response = provider.generate(
        LLMRequest(
            messages=[
                LLMMessage(
                    role="user",
                    content="Create a retrieval plan for the claim: The Boston Celtics won the 2024 NBA Finals.",
                )
            ],
            temperature=0.0,
            response_format="json",
        )
    )

    payload = json.loads(response.content)

    assert payload["source_candidates"]
    assert payload["queries"]
    assert payload["source_candidates"][0]["domain"] == "nba.com"


def test_dev_deterministic_provider_returns_supports_stance():
    provider = DevDeterministicLLMProvider()

    response = provider.generate(
        LLMRequest(
            messages=[
                LLMMessage(
                    role="user",
                    content=(
                        "Classify the relationship between CLAIM and EVIDENCE. "
                        "Claim: The Boston Celtics won the 2024 NBA Finals. "
                        "Evidence: The Boston Celtics won the 2024 NBA Finals."
                    ),
                )
            ],
            temperature=0.0,
            response_format="json",
        )
    )

    payload = json.loads(response.content)

    assert payload["stance"] == "supports"
    assert payload["confidence"] >= 0.9


def test_dev_deterministic_provider_detects_generic_claim_evidence_stance_prompt():
    provider = DevDeterministicLLMProvider()

    response = provider.generate(
        LLMRequest(
            messages=[
                LLMMessage(
                    role="system",
                    content="You classify whether evidence supports, contradicts, or is insufficient for a claim.",
                ),
                LLMMessage(
                    role="user",
                    content=(
                        "CLAIM: The Boston Celtics won the 2024 NBA Finals.\\n"
                        "EVIDENCE: 2024 NBA Finals page. The Boston Celtics defeated the Dallas Mavericks "
                        "and won the NBA Finals championship title."
                    ),
                ),
            ],
            temperature=0.0,
            response_format="json",
        )
    )

    payload = json.loads(response.content)

    assert payload["stance"] == "supports"
    assert payload["confidence"] >= 0.9
