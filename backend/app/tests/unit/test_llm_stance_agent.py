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


class InsufficientStanceLLMProvider(LLMProvider):
    name = "insufficient_stance_llm"

    def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content='{"stance_label":"insufficient","confidence":0.4,"rationale":"Not enough information."}',
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


def test_llm_stance_agent_overrides_insufficient_for_score_contradiction():
    claim = AtomicClaim(
        claim_id="claim_score",
        claim_text="Belgium beats USA with a 3-1 win in the Round of 16",
        claim_type=ClaimType.RESULT,
        confidence=0.9,
    )
    evidence = EvidenceItem(
        evidence_id="evidence_score",
        claim_id="claim_score",
        source_id="source_news",
        title="Belgium defeats United States",
        evidence_text=(
            "Belgium's 4-1 victory over the United States in the Round of 16 "
            "sent the U.S. team out of the tournament."
        ),
        reliability=0.9,
        independence=0.8,
        freshness=0.8,
        specificity=0.95,
    )

    output = LLMStanceAgent(llm_provider=InsufficientStanceLLMProvider()).run(
        LLMStanceInput(claim=claim, evidence=evidence)
    )

    assert output.stance.stance == StanceLabel.CONTRADICTS
    assert output.stance.confidence == 0.9
