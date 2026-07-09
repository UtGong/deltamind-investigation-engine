from app.algorithm.pivot.scoring import PivotThresholds, score_claim
from app.core.constants import StanceLabel, VerdictLabel
from app.schemas.agent import EvidenceItem, StanceResult


def test_supported_claim():
    evidence = [
        EvidenceItem(
            evidence_id="E1",
            claim_id="C1",
            source_id="S1",
            evidence_text="Official source confirms the claim.",
            reliability=0.95,
            independence=1.0,
            freshness=0.95,
            specificity=0.95,
        )
    ]

    stances = [
        StanceResult(
            claim_id="C1",
            evidence_id="E1",
            stance=StanceLabel.SUPPORTS,
            confidence=0.95,
            reason="Evidence directly supports the claim.",
        )
    ]

    verdict = score_claim("C1", evidence, stances)

    assert verdict.verdict == VerdictLabel.SUPPORTED
    assert verdict.support_score > verdict.contradiction_score


def test_contradicted_claim():
    evidence = [
        EvidenceItem(
            evidence_id="E1",
            claim_id="C1",
            source_id="S1",
            evidence_text="Official source contradicts the claim.",
            reliability=0.95,
            independence=1.0,
            freshness=0.95,
            specificity=0.95,
        )
    ]

    stances = [
        StanceResult(
            claim_id="C1",
            evidence_id="E1",
            stance=StanceLabel.CONTRADICTS,
            confidence=0.95,
            reason="Evidence directly contradicts the claim.",
        )
    ]

    verdict = score_claim("C1", evidence, stances)

    assert verdict.verdict == VerdictLabel.CONTRADICTED
    assert verdict.contradiction_score > verdict.support_score


def test_score_contradiction_threshold_accepts_lower_quality_direct_evidence():
    evidence = [
        EvidenceItem(
            evidence_id="E_score",
            claim_id="C1",
            source_id="S_reuters",
            evidence_text="USA loses 4-1 in World Cup round of 16 against Belgium.",
            reliability=0.35,
            independence=0.7,
            freshness=0.6,
            specificity=0.8,
        )
    ]
    stances = [
        StanceResult(
            claim_id="C1",
            evidence_id="E_score",
            stance=StanceLabel.CONTRADICTS,
            confidence=0.9,
            reason="The evidence reports the same matchup with a different score.",
        )
    ]

    verdict = score_claim("C1", evidence, stances)

    assert verdict.verdict == VerdictLabel.CONTRADICTED
    assert verdict.contradiction_score >= PivotThresholds().contradicted_min


def test_structured_numeric_support_threshold_accepts_lower_quality_direct_evidence():
    evidence = [
        EvidenceItem(
            evidence_id="E_score",
            claim_id="C1",
            source_id="S_reuters",
            evidence_text="Team A defeated Team B 4-1.",
            reliability=0.35,
            independence=0.7,
            freshness=0.6,
            specificity=0.8,
        )
    ]
    stances = [
        StanceResult(
            claim_id="C1",
            evidence_id="E_score",
            stance=StanceLabel.SUPPORTS,
            confidence=0.9,
            reason="The evidence states the same match winner and score as the claim.",
        )
    ]

    verdict = score_claim("C1", evidence, stances)

    assert verdict.verdict == VerdictLabel.SUPPORTED
    assert verdict.support_score >= PivotThresholds().supported_min


def test_strong_support_not_overruled_by_insufficient_noise():
    evidence = [
        EvidenceItem(
            evidence_id="E_support",
            claim_id="C1",
            source_id="S_example",
            evidence_text="The Team Green won the 2024 Example Final.",
            reliability=0.945,
            independence=0.7,
            freshness=0.6,
            specificity=0.7,
        ),
        EvidenceItem(
            evidence_id="E_noise_1",
            claim_id="C1",
            source_id="S_example",
            evidence_text="Navigation page with weak search text.",
            reliability=0.945,
            independence=0.7,
            freshness=0.6,
            specificity=0.7,
        ),
        EvidenceItem(
            evidence_id="E_noise_2",
            claim_id="C1",
            source_id="S_example",
            evidence_text="Another search/navigation page.",
            reliability=0.945,
            independence=0.7,
            freshness=0.6,
            specificity=0.7,
        ),
        EvidenceItem(
            evidence_id="E_noise_3",
            claim_id="C1",
            source_id="S_example",
            evidence_text="A broad example news page.",
            reliability=0.945,
            independence=0.7,
            freshness=0.6,
            specificity=0.7,
        ),
    ]

    stances = [
        StanceResult(
            claim_id="C1",
            evidence_id="E_support",
            stance=StanceLabel.SUPPORTS,
            confidence=0.98,
            reason="Directly supports the claim.",
        ),
        StanceResult(
            claim_id="C1",
            evidence_id="E_noise_1",
            stance=StanceLabel.INSUFFICIENT,
            confidence=0.95,
            reason="Search page is insufficient.",
        ),
        StanceResult(
            claim_id="C1",
            evidence_id="E_noise_2",
            stance=StanceLabel.INSUFFICIENT,
            confidence=0.95,
            reason="Search page is insufficient.",
        ),
        StanceResult(
            claim_id="C1",
            evidence_id="E_noise_3",
            stance=StanceLabel.INSUFFICIENT,
            confidence=0.95,
            reason="News page is insufficient.",
        ),
    ]

    verdict = score_claim("C1", evidence, stances)

    assert verdict.verdict == VerdictLabel.SUPPORTED
    assert verdict.support_score >= 0.65
    assert verdict.confidence >= 0.5
    assert verdict.debug["decisive_stance_count"] == 1
    assert verdict.debug["weak_or_irrelevant_count"] == 3


def test_only_insufficient_evidence_remains_unverifiable():
    evidence = [
        EvidenceItem(
            evidence_id="E1",
            claim_id="C1",
            source_id="S1",
            evidence_text="Navigation text without claim-specific evidence.",
            reliability=0.9,
            independence=0.7,
            freshness=0.6,
            specificity=0.4,
        )
    ]

    stances = [
        StanceResult(
            claim_id="C1",
            evidence_id="E1",
            stance=StanceLabel.INSUFFICIENT,
            confidence=0.95,
            reason="Insufficient evidence.",
        )
    ]

    verdict = score_claim("C1", evidence, stances)

    assert verdict.verdict == VerdictLabel.UNVERIFIABLE
    assert verdict.support_score == 0.0
    assert verdict.contradiction_score == 0.0
    assert verdict.uncertainty_score > 0.75


def test_strong_support_not_overruled_by_insufficient_noise():
    evidence = [
        EvidenceItem(
            evidence_id="E_support",
            claim_id="C1",
            source_id="S_example",
            evidence_text="The Team Green won the 2024 Example Final.",
            reliability=0.945,
            independence=0.7,
            freshness=0.6,
            specificity=0.7,
        ),
        EvidenceItem(
            evidence_id="E_noise_1",
            claim_id="C1",
            source_id="S_example",
            evidence_text="Navigation page with weak search text.",
            reliability=0.945,
            independence=0.7,
            freshness=0.6,
            specificity=0.7,
        ),
        EvidenceItem(
            evidence_id="E_noise_2",
            claim_id="C1",
            source_id="S_example",
            evidence_text="Another search/navigation page.",
            reliability=0.945,
            independence=0.7,
            freshness=0.6,
            specificity=0.7,
        ),
        EvidenceItem(
            evidence_id="E_noise_3",
            claim_id="C1",
            source_id="S_example",
            evidence_text="A broad example news page.",
            reliability=0.945,
            independence=0.7,
            freshness=0.6,
            specificity=0.7,
        ),
    ]

    stances = [
        StanceResult(
            claim_id="C1",
            evidence_id="E_support",
            stance=StanceLabel.SUPPORTS,
            confidence=0.98,
            reason="Directly supports the claim.",
        ),
        StanceResult(
            claim_id="C1",
            evidence_id="E_noise_1",
            stance=StanceLabel.INSUFFICIENT,
            confidence=0.95,
            reason="Search page is insufficient.",
        ),
        StanceResult(
            claim_id="C1",
            evidence_id="E_noise_2",
            stance=StanceLabel.INSUFFICIENT,
            confidence=0.95,
            reason="Search page is insufficient.",
        ),
        StanceResult(
            claim_id="C1",
            evidence_id="E_noise_3",
            stance=StanceLabel.INSUFFICIENT,
            confidence=0.95,
            reason="News page is insufficient.",
        ),
    ]

    verdict = score_claim("C1", evidence, stances)

    assert verdict.verdict == VerdictLabel.SUPPORTED
    assert verdict.support_score >= 0.65
    assert verdict.confidence >= 0.5
    assert verdict.debug["decisive_stance_count"] == 1
    assert verdict.debug["weak_or_irrelevant_count"] == 3


def test_only_insufficient_evidence_remains_unverifiable():
    evidence = [
        EvidenceItem(
            evidence_id="E1",
            claim_id="C1",
            source_id="S1",
            evidence_text="Navigation text without claim-specific evidence.",
            reliability=0.9,
            independence=0.7,
            freshness=0.6,
            specificity=0.4,
        )
    ]

    stances = [
        StanceResult(
            claim_id="C1",
            evidence_id="E1",
            stance=StanceLabel.INSUFFICIENT,
            confidence=0.95,
            reason="Insufficient evidence.",
        )
    ]

    verdict = score_claim("C1", evidence, stances)

    assert verdict.verdict == VerdictLabel.UNVERIFIABLE
    assert verdict.support_score == 0.0
    assert verdict.contradiction_score == 0.0
    assert verdict.uncertainty_score > 0.75
