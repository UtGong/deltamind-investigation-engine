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
