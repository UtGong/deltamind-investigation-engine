from app.agents.claim_correction_agent import (
    ClaimCorrectionAgent,
    ClaimCorrectionInput,
)
from app.core.constants import ClaimType, StanceLabel, VerdictLabel
from app.schemas.agent import AtomicClaim, EvidenceItem, PivotVerdict, StanceResult


def test_claim_correction_agent_corrects_2023_heat_winner_claim():
    claim = AtomicClaim(
        claim_id="C1",
        claim_text="The Miami Heat won the 2023 NBA Finals.",
        claim_type=ClaimType.EVENT,
        subject="Miami Heat",
        predicate="won",
        object="2023 NBA Finals",
        confidence=1.0,
    )

    evidence = [
        EvidenceItem(
            evidence_id="E1",
            claim_id="C1",
            source_id="source_nba",
            url="https://www.nba.com/playoffs/2023/nba-finals",
            title="2023 NBA Finals",
            evidence_text=(
                "The Denver Nuggets defeated the Miami Heat in the 2023 NBA Finals."
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
            reason="Evidence states Denver won, not Miami.",
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
    assert correction.corrected_claim == "The Denver Nuggets won the 2023 NBA Finals."
    assert correction.correction_type == "entity_replacement"
    assert correction.changed_fields[0].original == "Miami Heat"
    assert correction.changed_fields[0].corrected == "Denver Nuggets"
    assert correction.evidence_ids == ["E1"]


def test_claim_correction_agent_does_not_correct_unverifiable_secret_claim():
    claim = AtomicClaim(
        claim_id="C2",
        claim_text="A secret injury caused the Boston Celtics to win the 2024 NBA Finals.",
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
