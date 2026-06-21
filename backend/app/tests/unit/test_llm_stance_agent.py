from app.agents.llm_stance_agent import LLMStanceAgent, LLMStanceInput
from app.core.constants import ClaimType, StanceLabel
from app.providers.llm.base import LLMProvider
from app.schemas.agent import AtomicClaim, EvidenceItem
from app.schemas.llm import LLMRequest, LLMResponse


class FakeStanceLLMProvider(LLMProvider):
    name = "fake_stance_llm"

    def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content='{"stance_label":"supports","confidence":0.91,"rationale":"The evidence directly states the claim."}',
            provider=self.name,
            model="fake-model",
            input_tokens=10,
            output_tokens=5,
            estimated_cost_usd=0.0,
        )


def make_claim() -> AtomicClaim:
    return AtomicClaim(
        claim_id="claim_1",
        claim_text="Team A won the final 3-1.",
        claim_type=ClaimType.RESULT,
        confidence=0.9,
    )


def make_evidence() -> EvidenceItem:
    return EvidenceItem(
        evidence_id="evidence_1",
        claim_id="claim_1",
        source_id="source_1",
        url="https://example.com",
        title="Example source",
        evidence_text="Team A won the final 3-1.",
        independence_group="example.com",
        reliability=0.9,
        independence=0.8,
        freshness=0.7,
        specificity=0.95,
    )


def test_llm_stance_agent_parses_supports_response():
    agent = LLMStanceAgent(llm_provider=FakeStanceLLMProvider())

    output = agent.run(
        LLMStanceInput(
            claim=make_claim(),
            evidence=make_evidence(),
        )
    )

    assert output.raw_response.provider == "fake_stance_llm"
    assert output.stance.claim_id == "claim_1"
    assert output.stance.evidence_id == "evidence_1"
    assert output.stance.stance == StanceLabel.SUPPORTS
    assert output.stance.confidence == 0.91
