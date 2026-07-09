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


class TimeoutStanceLLMProvider(LLMProvider):
    name = "timeout_stance_llm"

    def generate(self, request: LLMRequest) -> LLMResponse:
        raise TimeoutError("timed out")


class ExplodingStanceLLMProvider(LLMProvider):
    name = "exploding_stance_llm"

    def generate(self, request: LLMRequest) -> LLMResponse:
        raise AssertionError("LLM should not be called for deterministic score stance")


def make_claim() -> AtomicClaim:
    return AtomicClaim(
        claim_id="claim_1",
        claim_text="Team A won the final.",
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
        evidence_text="Team A won the final.",
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


def test_llm_stance_agent_skips_llm_for_score_contradiction():
    claim = AtomicClaim(
        claim_id="claim_score",
        claim_text="Belgium beats USA with a 3-1 win in the Round of 16",
        claim_type=ClaimType.RESULT,
        confidence=0.9,
    )
    evidence = EvidenceItem(
        evidence_id="evidence_score",
        claim_id="claim_score",
        source_id="source_fifa",
        title="USA 1-4 Belgium | Result, Stats & Highlights",
        evidence_text="USA 1-4 Belgium in the Round of 16 at the FIFA World Cup 2026.",
        reliability=0.9,
        independence=0.8,
        freshness=0.8,
        specificity=0.95,
    )

    output = LLMStanceAgent(llm_provider=ExplodingStanceLLMProvider()).run(
        LLMStanceInput(claim=claim, evidence=evidence)
    )

    assert output.raw_response.provider == "internal_deterministic"
    assert output.raw_response.metadata["llm_used"] is False
    assert output.stance.stance == StanceLabel.CONTRADICTS
    assert output.stance.confidence == 0.9


def test_llm_stance_agent_skips_llm_for_non_comparable_score_evidence():
    claim = AtomicClaim(
        claim_id="claim_score",
        claim_text="Belgium beats USA with a 3-1 win in the Round of 16",
        claim_type=ClaimType.RESULT,
        confidence=0.9,
    )
    evidence = EvidenceItem(
        evidence_id="evidence_generic",
        claim_id="claim_score",
        source_id="source_reuters",
        title="United States vs. Belgium: Live match at FIFA World Cup 2026",
        evidence_text="Live coverage and tournament information for United States vs. Belgium.",
        reliability=0.8,
        independence=0.8,
        freshness=0.8,
        specificity=0.5,
    )

    output = LLMStanceAgent(llm_provider=ExplodingStanceLLMProvider()).run(
        LLMStanceInput(claim=claim, evidence=evidence)
    )

    assert output.raw_response.provider == "internal_deterministic"
    assert output.raw_response.metadata["llm_used"] is False
    assert output.raw_response.metadata["fallback_reason"] == (
        "score_claim_without_comparable_score_evidence"
    )


def test_llm_stance_agent_skips_llm_for_round_contradiction():
    claim = AtomicClaim(
        claim_id="claim_round",
        claim_text="The match took place in the Round of 9.",
        claim_type=ClaimType.RESULT,
        confidence=0.9,
    )
    evidence = EvidenceItem(
        evidence_id="evidence_round",
        claim_id="claim_round",
        source_id="source_news",
        title="USA soccer's FIFA World Cup run ends with ugly loss vs Belgium",
        evidence_text=(
            "USA loses 4-1 in World Cup round of 16 against Belgium, "
            "ending the Americans' 2026 run."
        ),
        reliability=0.9,
        independence=0.8,
        freshness=0.8,
        specificity=0.95,
    )

    output = LLMStanceAgent(llm_provider=ExplodingStanceLLMProvider()).run(
        LLMStanceInput(claim=claim, evidence=evidence)
    )

    assert output.raw_response.provider == "internal_deterministic"
    assert output.raw_response.model == "round-fact-stance-v1"
    assert output.raw_response.metadata["llm_used"] is False
    assert output.stance.stance == StanceLabel.CONTRADICTS
    assert output.stance.confidence == 0.9


def test_llm_stance_agent_skips_llm_for_non_comparable_round_evidence():
    claim = AtomicClaim(
        claim_id="claim_round",
        claim_text="The match took place in the Round of 9.",
        claim_type=ClaimType.RESULT,
        confidence=0.9,
    )
    evidence = EvidenceItem(
        evidence_id="evidence_generic",
        claim_id="claim_round",
        source_id="source_news",
        title="Belgium vs USA preview",
        evidence_text="A preview of the 2026 tournament matchup.",
        reliability=0.8,
        independence=0.8,
        freshness=0.8,
        specificity=0.5,
    )

    output = LLMStanceAgent(llm_provider=ExplodingStanceLLMProvider()).run(
        LLMStanceInput(claim=claim, evidence=evidence)
    )

    assert output.raw_response.provider == "internal_deterministic"
    assert output.raw_response.model == "round-claim-fallback-stance-v1"
    assert output.raw_response.metadata["llm_used"] is False
    assert output.raw_response.metadata["fallback_reason"] == (
        "round_claim_without_comparable_round_evidence"
    )


def test_llm_stance_agent_skips_llm_for_score_atom_without_matchup():
    claim = AtomicClaim(
        claim_id="claim_score_fragment",
        claim_text="Belgium won the match with a score of 3-1",
        claim_type=ClaimType.RESULT,
        confidence=0.9,
    )
    evidence = EvidenceItem(
        evidence_id="evidence_score",
        claim_id="claim_score_fragment",
        source_id="source_fifa",
        title="USA 1-4 Belgium | Result, Stats & Highlights",
        evidence_text="USA 1-4 Belgium in the Round of 16 at the FIFA World Cup 2026.",
        reliability=0.9,
        independence=0.8,
        freshness=0.8,
        specificity=0.95,
    )

    output = LLMStanceAgent(llm_provider=ExplodingStanceLLMProvider()).run(
        LLMStanceInput(claim=claim, evidence=evidence)
    )

    assert output.raw_response.provider == "internal_deterministic"
    assert output.raw_response.metadata["llm_used"] is False


def test_llm_stance_agent_falls_back_when_provider_times_out():
    agent = LLMStanceAgent(llm_provider=TimeoutStanceLLMProvider())

    output = agent.run(
        LLMStanceInput(
            claim=make_claim(),
            evidence=make_evidence(),
        )
    )

    assert output.raw_response.provider == "timeout_stance_llm"
    assert output.raw_response.model == "fallback_local_stance"
    assert output.raw_response.metadata["fallback_used"] is True
    assert output.raw_response.metadata["error_type"] == "TimeoutError"
    assert output.stance.stance == StanceLabel.SUPPORTS
    assert output.stance.confidence == 0.72
