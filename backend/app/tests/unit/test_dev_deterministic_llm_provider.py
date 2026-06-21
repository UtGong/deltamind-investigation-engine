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


def test_dev_deterministic_provider_decomposes_rigged_claim_without_defaulting_to_celtics():
    provider = DevDeterministicLLMProvider()

    response = provider.generate(
        LLMRequest(
            messages=[
                LLMMessage(
                    role="user",
                    content=(
                        "Decompose this claim into atomic claims. "
                        "Claim: The 2024 NBA Finals were rigged by an unnamed official."
                    ),
                )
            ],
            temperature=0.0,
            response_format="json",
        )
    )

    payload = json.loads(response.content)
    claim = payload["claims"][0]

    assert claim["claim_text"] == "The 2024 NBA Finals were rigged by an unnamed official."
    assert claim["predicate"] == "alleges"
    assert "Boston Celtics won" not in claim["claim_text"]


def test_dev_deterministic_provider_decomposes_2023_nuggets_claim():
    provider = DevDeterministicLLMProvider()

    response = provider.generate(
        LLMRequest(
            messages=[
                LLMMessage(
                    role="user",
                    content=(
                        "Decompose this claim into atomic claims. "
                        "Claim: The Denver Nuggets won the 2023 NBA Finals."
                    ),
                )
            ],
            temperature=0.0,
            response_format="json",
        )
    )

    payload = json.loads(response.content)
    claim = payload["claims"][0]

    assert claim["claim_text"] == "The Denver Nuggets won the 2023 NBA Finals."
    assert claim["subject"] == "The Denver Nuggets"
    assert claim["object"] == "the 2023 NBA Finals"


def test_dev_deterministic_provider_search_plan_includes_2023_finals_url():
    provider = DevDeterministicLLMProvider()

    response = provider.generate(
        LLMRequest(
            messages=[
                LLMMessage(
                    role="user",
                    content=(
                        "Create a retrieval plan for this claim. "
                        "Claim: The Denver Nuggets won the 2023 NBA Finals."
                    ),
                )
            ],
            temperature=0.0,
            response_format="json",
        )
    )

    payload = json.loads(response.content)
    urls = [
        candidate.get("url")
        for candidate in payload["source_candidates"]
        if candidate.get("url")
    ]

    assert "https://www.nba.com/playoffs/2023/nba-finals" in urls
