from app.agents.llm_claim_decomposition_agent import (
    LLMClaimDecompositionAgent,
    LLMClaimDecompositionInput,
)
from app.core.constants import ClaimType
from app.schemas.llm import LLMRequest, LLMResponse


class ListReturningLLMProvider:
    name = "list_returning_llm_provider"
    model = "test-model"

    def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content=(
                '[{"claim_text":"Player X joined Club A on June 10.",'
                '"claim_type":"transfer",'
                '"subject":"Player X",'
                '"predicate":"joined",'
                '"object":"Club A",'
                '"confidence":0.8}]'
            ),
            provider=self.name,
            model=self.model,
        )


class LooseGeminiStyleLLMProvider:
    name = "loose_gemini_style_provider"
    model = "test-model"

    def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content=(
                '{'
                '"claims": ['
                '{"claim_text":"Player X joined Club A on June 10.",'
                '"claim_type":"fact",'
                '"subject":"Player X",'
                '"predicate":"joined",'
                '"object":"Club A on June 10",'
                '"confidence":"high"},'
                '{"claim_text":"Team A won the final 3-1.",'
                '"claim_type":"fact",'
                '"subject":"Team A",'
                '"predicate":"won",'
                '"object":"the final 3-1",'
                '"confidence":"high"},'
                '{"claim_text":"Player Y is injured.",'
                '"claim_type":"fact",'
                '"subject":"Player Y",'
                '"predicate":"is",'
                '"object":"injured",'
                '"confidence":"high"}'
                ']'
                '}'
            ),
            provider=self.name,
            model=self.model,
        )


def test_llm_claim_decomposition_agent_with_mock_provider():
    agent = LLMClaimDecompositionAgent()

    output = agent.run(
        LLMClaimDecompositionInput(
            case_id="case_1",
            input_text="Player X joined Club A on June 10.",
        )
    )

    assert len(output.claims) == 1
    assert output.claims[0].claim_id == "case_1_claim_1"
    assert output.claims[0].claim_type == ClaimType.TRANSFER
    assert output.raw_response.provider == "mock_llm_provider"


def test_llm_claim_decomposition_agent_handles_multiple_sentences():
    agent = LLMClaimDecompositionAgent()

    output = agent.run(
        LLMClaimDecompositionInput(
            case_id="case_2",
            input_text=(
                "Player X joined Club A on June 10. "
                "Team A won the final 3-1. "
                "Player Y is injured."
            ),
        )
    )

    assert len(output.claims) == 3
    assert output.claims[0].claim_type == ClaimType.TRANSFER
    assert output.claims[1].claim_type == ClaimType.RESULT
    assert output.claims[2].claim_type == ClaimType.INJURY


def test_llm_claim_decomposition_agent_accepts_top_level_list():
    agent = LLMClaimDecompositionAgent(llm_provider=ListReturningLLMProvider())

    output = agent.run(
        LLMClaimDecompositionInput(
            case_id="case_3",
            input_text="Player X joined Club A on June 10.",
        )
    )

    assert len(output.claims) == 1
    assert output.claims[0].claim_type == ClaimType.TRANSFER
    assert output.claims[0].subject == "Player X"


def test_llm_claim_decomposition_agent_normalizes_loose_gemini_output():
    agent = LLMClaimDecompositionAgent(llm_provider=LooseGeminiStyleLLMProvider())

    output = agent.run(
        LLMClaimDecompositionInput(
            case_id="case_4",
            input_text=(
                "Player X joined Club A on June 10. "
                "Team A won the final 3-1. "
                "Player Y is injured."
            ),
        )
    )

    assert len(output.claims) == 3
    assert output.claims[0].claim_type == ClaimType.TRANSFER
    assert output.claims[1].claim_type == ClaimType.RESULT
    assert output.claims[2].claim_type == ClaimType.INJURY
    assert output.claims[0].confidence == 0.9
