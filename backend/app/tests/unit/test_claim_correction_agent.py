from app.agents.claim_correction_agent import (
    ClaimCorrectionAgent,
    ClaimCorrectionInput,
)
from app.schemas.llm import LLMResponse
from app.core.constants import ClaimType, StanceLabel, VerdictLabel
from app.schemas.agent import AtomicClaim, EvidenceItem, PivotVerdict, StanceResult


class CorrectionProvider:
    name = "test_correction_provider"
    model = "test-model"

    def generate(self, request):
        return LLMResponse(
            content=(
                '{"needs_correction": true, '
                '"corrected_claim": "The Team Blue won the 2023 Example Final.", '
                '"correction_type": "entity_replacement", '
                '"changed_fields": [{"field": "subject", "original": "Team Red", "corrected": "Team Blue"}], '
                '"confidence": 0.82, '
                '"evidence_ids": ["E1"], '
                '"rationale": "Evidence identifies Team Blue as the winner."}'
            ),
            provider=self.name,
            model=self.model,
        )


class ExplodingCorrectionProvider:
    name = "exploding_correction_provider"

    def generate(self, request):
        raise AssertionError("LLM should not be called for deterministic score correction")


def test_claim_correction_agent_uses_llm_provider_for_correction():
    claim = AtomicClaim(
        claim_id="C1",
        claim_text="The Team Red won the 2023 Example Final.",
        claim_type=ClaimType.EVENT,
        subject="Team Red",
        predicate="won",
        object="2023 Example Final",
        confidence=1.0,
    )

    evidence = [
        EvidenceItem(
            evidence_id="E1",
            claim_id="C1",
            source_id="source_example",
            url="https://www.example.org/playoffs/2023/example-final",
            title="2023 Example Final",
            evidence_text=(
                "The Team Blue defeated the Team Red in the 2023 Example Final."
            ),
            reliability=0.945,
            specificity=0.9,
        )
    ]

    stances = [
        StanceResult(
            claim_id="C1",
            evidence_id="E1",
            stance=StanceLabel.CONTRADICTS,
            confidence=0.92,
            reason="Evidence identifies Team Blue as winner, not Team Red.",
        )
    ]

    verdict = PivotVerdict(
        claim_id="C1",
        verdict=VerdictLabel.CONTRADICTED,
        confidence=0.6267,
        support_score=0.0,
        contradiction_score=0.6267,
        uncertainty_score=0.3,
        reason="The claim is contradicted by the available evidence.",
    )

    output = ClaimCorrectionAgent(llm_provider=CorrectionProvider()).run(
        ClaimCorrectionInput(
            claim=claim,
            evidence=evidence,
            stances=stances,
            verdict=verdict,
        )
    )

    correction = output.correction

    assert correction.needs_correction is True
    assert correction.corrected_claim == "The Team Blue won the 2023 Example Final."
    assert correction.correction_type == "entity_replacement"
    assert correction.changed_fields[0].original == "Team Red"
    assert correction.changed_fields[0].corrected == "Team Blue"
    assert correction.evidence_ids == ["E1"]


def test_claim_correction_agent_does_not_correct_unverifiable_secret_claim():
    claim = AtomicClaim(
        claim_id="C2",
        claim_text="A secret injury caused the Team Green to win the 2024 Example Final.",
        claim_type=ClaimType.CAUSAL,
        confidence=1.0,
    )

    verdict = PivotVerdict(
        claim_id="C2",
        verdict=VerdictLabel.UNVERIFIABLE,
        confidence=0.0,
        support_score=0.0,
        contradiction_score=0.0,
        uncertainty_score=1.0,
        reason="The causal claim is not supported by available evidence.",
    )

    output = ClaimCorrectionAgent().run(
        ClaimCorrectionInput(
            claim=claim,
            evidence=[],
            stances=[],
            verdict=verdict,
        )
    )

    correction = output.correction

    assert correction.needs_correction is False
    assert correction.corrected_claim is None
    assert correction.correction_type == "none"


def test_claim_correction_agent_falls_back_to_score_correction_when_llm_declines():
    claim = AtomicClaim(
        claim_id="C3",
        claim_text="Belgium beats USA with a 3-1 win in the Round of 16",
        claim_type=ClaimType.RESULT,
        subject="Belgium",
        predicate="beats",
        object="USA 3-1 Round of 16",
        confidence=1.0,
    )
    evidence = [
        EvidenceItem(
            evidence_id="E3",
            claim_id="C3",
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
    ]
    stances = [
        StanceResult(
            claim_id="C3",
            evidence_id="E3",
            stance=StanceLabel.CONTRADICTS,
            confidence=0.9,
            reason="The evidence reports the same matchup with a 4-1 score.",
        )
    ]
    verdict = PivotVerdict(
        claim_id="C3",
        verdict=VerdictLabel.CONTRADICTED,
        confidence=0.8,
        support_score=0.0,
        contradiction_score=0.8,
        uncertainty_score=0.2,
        reason="The claim is contradicted by the available evidence.",
    )

    output = ClaimCorrectionAgent().run(
        ClaimCorrectionInput(
            claim=claim,
            evidence=evidence,
            stances=stances,
            verdict=verdict,
        )
    )

    correction = output.correction
    assert correction.needs_correction is True
    assert correction.corrected_claim == "Belgium beats USA with a 4-1 win in the Round of 16"
    assert correction.correction_type == "numeric_correction"
    assert correction.changed_fields[0].original == "3-1"
    assert correction.changed_fields[0].corrected == "4-1"
    assert correction.evidence_ids == ["E3"]


def test_claim_correction_agent_skips_llm_for_score_correction():
    claim = AtomicClaim(
        claim_id="C4",
        claim_text="Belgium beats USA with a 3-1 win in the Round of 16",
        claim_type=ClaimType.RESULT,
        subject="Belgium",
        predicate="beats",
        object="USA 3-1 Round of 16",
        confidence=1.0,
    )
    evidence = [
        EvidenceItem(
            evidence_id="E4",
            claim_id="C4",
            source_id="source_fifa",
            title="USA 1-4 Belgium | Result, Stats & Highlights",
            evidence_text="USA 1-4 Belgium in the Round of 16 at the FIFA World Cup 2026.",
            reliability=0.9,
            independence=0.8,
            freshness=0.8,
            specificity=0.95,
        )
    ]
    stances = [
        StanceResult(
            claim_id="C4",
            evidence_id="E4",
            stance=StanceLabel.CONTRADICTS,
            confidence=0.9,
            reason="The evidence reports the same matchup with a 4-1 score.",
        )
    ]
    verdict = PivotVerdict(
        claim_id="C4",
        verdict=VerdictLabel.CONTRADICTED,
        confidence=0.8,
        support_score=0.0,
        contradiction_score=0.8,
        uncertainty_score=0.2,
        reason="The claim is contradicted by the available evidence.",
    )

    output = ClaimCorrectionAgent(llm_provider=ExplodingCorrectionProvider()).run(
        ClaimCorrectionInput(
            claim=claim,
            evidence=evidence,
            stances=stances,
            verdict=verdict,
        )
    )

    assert output.raw_response is None
    assert output.correction.needs_correction is True
    assert output.correction.corrected_claim == (
        "Belgium beats USA with a 4-1 win in the Round of 16"
    )


def test_claim_correction_agent_skips_llm_for_round_correction():
    claim = AtomicClaim(
        claim_id="C5",
        claim_text="Belgium beats USA with a 4-1 win in the Round of 9 in Worldcup 2026",
        claim_type=ClaimType.RESULT,
        subject="Belgium",
        predicate="beats",
        object="USA 4-1 Round of 9",
        confidence=1.0,
    )
    evidence = [
        EvidenceItem(
            evidence_id="E5",
            claim_id="C5",
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
    ]
    stances = [
        StanceResult(
            claim_id="C5",
            evidence_id="E5",
            stance=StanceLabel.CONTRADICTS,
            confidence=0.9,
            reason="The evidence states the same event with a different round.",
        )
    ]
    verdict = PivotVerdict(
        claim_id="C5",
        verdict=VerdictLabel.CONTRADICTED,
        confidence=0.8,
        support_score=0.0,
        contradiction_score=0.8,
        uncertainty_score=0.2,
        reason="The claim is contradicted by the available evidence.",
    )

    output = ClaimCorrectionAgent(llm_provider=ExplodingCorrectionProvider()).run(
        ClaimCorrectionInput(
            claim=claim,
            evidence=evidence,
            stances=stances,
            verdict=verdict,
        )
    )

    assert output.raw_response is None
    assert output.correction.needs_correction is True
    assert output.correction.corrected_claim == (
        "Belgium beats USA with a 4-1 win in the Round of 16 in Worldcup 2026"
    )
    assert output.correction.correction_type == "scope_correction"
    assert output.correction.changed_fields[0].field == "round"
    assert output.correction.changed_fields[0].original == "Round of 9"
    assert output.correction.changed_fields[0].corrected == "Round of 16"
