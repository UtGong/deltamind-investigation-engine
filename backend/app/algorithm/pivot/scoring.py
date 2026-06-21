from dataclasses import dataclass

from app.core.constants import StanceLabel, VerdictLabel
from app.schemas.agent import EvidenceItem, PivotVerdict, StanceResult


@dataclass(frozen=True)
class PivotThresholds:
    supported_min: float = 0.55
    contradicted_min: float = 0.55
    contested_min: float = 0.55
    partial_min: float = 0.40
    low_evidence_max: float = 0.25


def _evidence_weight(evidence: EvidenceItem) -> float:
    """Estimate evidence quality without over-penalizing one weak dimension.

    The previous multiplicative formula made useful official evidence too small:
    reliability * independence * freshness * specificity.

    For verification, reliability and specificity should dominate. Independence and
    freshness still matter, but they should usually reduce trust, not erase an
    otherwise directly relevant official source.
    """

    return (
        evidence.reliability * 0.45
        + evidence.specificity * 0.35
        + evidence.independence * 0.10
        + evidence.freshness * 0.10
    )


def score_claim(
    claim_id: str,
    evidence_items: list[EvidenceItem],
    stance_results: list[StanceResult],
    thresholds: PivotThresholds | None = None,
) -> PivotVerdict:
    thresholds = thresholds or PivotThresholds()

    evidence_by_id = {item.evidence_id: item for item in evidence_items}
    relevant_stances = [stance for stance in stance_results if stance.claim_id == claim_id]

    support_score = 0.0
    contradiction_score = 0.0
    partial_support_score = 0.0
    weak_or_irrelevant_count = 0
    decisive_stance_count = 0

    for stance in relevant_stances:
        evidence = evidence_by_id.get(stance.evidence_id)
        if evidence is None:
            continue

        weighted_score = stance.confidence * _evidence_weight(evidence)

        if stance.stance == StanceLabel.SUPPORTS:
            support_score = _combine_signal_scores(support_score, weighted_score)
            decisive_stance_count += 1
        elif stance.stance == StanceLabel.CONTRADICTS:
            contradiction_score = _combine_signal_scores(
                contradiction_score,
                weighted_score,
            )
            decisive_stance_count += 1
        elif stance.stance == StanceLabel.PARTIALLY_SUPPORTS:
            partial_support_score = _combine_signal_scores(
                partial_support_score,
                weighted_score * 0.5,
            )
            decisive_stance_count += 1
        else:
            weak_or_irrelevant_count += 1

    support_score = _combine_signal_scores(support_score, partial_support_score)
    total_signal = max(support_score, contradiction_score)

    uncertainty_score = _calculate_uncertainty(
        total_signal=total_signal,
        weak_or_irrelevant_count=weak_or_irrelevant_count,
        decisive_stance_count=decisive_stance_count,
    )

    verdict, reason = _assign_verdict(
        support_score=support_score,
        contradiction_score=contradiction_score,
        uncertainty_score=uncertainty_score,
        thresholds=thresholds,
    )

    confidence = _calculate_confidence(
        support_score=support_score,
        contradiction_score=contradiction_score,
        uncertainty_score=uncertainty_score,
    )

    if verdict == VerdictLabel.SUPPORTED:
        confidence = round(max(confidence, support_score), 4)
    elif verdict == VerdictLabel.CONTRADICTED:
        confidence = round(max(confidence, contradiction_score), 4)

    return PivotVerdict(
        claim_id=claim_id,
        verdict=verdict,
        confidence=confidence,
        support_score=round(support_score, 4),
        contradiction_score=round(contradiction_score, 4),
        uncertainty_score=round(uncertainty_score, 4),
        reason=reason,
        debug={
            "total_stances": len(relevant_stances),
            "total_evidence": len(evidence_items),
            "decisive_stance_count": decisive_stance_count,
            "weak_or_irrelevant_count": weak_or_irrelevant_count,
        },
    )


def _combine_signal_scores(current_score: float, new_score: float) -> float:
    """Noisy-or aggregation.

    Multiple independent support signals should increase confidence but saturate
    at 1.0. This avoids unbounded additive scores while still allowing multiple
    pieces of evidence to reinforce the verdict.
    """

    current = max(0.0, min(1.0, current_score))
    new = max(0.0, min(1.0, new_score))

    return 1.0 - ((1.0 - current) * (1.0 - new))


def _calculate_uncertainty(
    total_signal: float,
    weak_or_irrelevant_count: int,
    decisive_stance_count: int,
) -> float:
    if decisive_stance_count == 0:
        missing_signal = max(0.0, 1.0 - total_signal)
        weak_signal_penalty = min(0.3, weak_or_irrelevant_count * 0.05)
        return max(0.0, min(1.0, missing_signal + weak_signal_penalty))

    missing_signal = max(0.0, 1.0 - total_signal)
    weak_signal_penalty = min(0.25, weak_or_irrelevant_count * 0.04)

    # Strong decisive evidence should lower uncertainty. Weak/irrelevant evidence
    # still matters, but should not cancel a direct support/contradiction stance.
    decisive_signal_discount = min(0.35, total_signal * 0.25)

    uncertainty = missing_signal + weak_signal_penalty - decisive_signal_discount

    return max(0.0, min(1.0, uncertainty))


def _assign_verdict(
    support_score: float,
    contradiction_score: float,
    uncertainty_score: float,
    thresholds: PivotThresholds,
) -> tuple[VerdictLabel, str]:
    if support_score >= thresholds.contested_min and contradiction_score >= thresholds.contested_min:
        return (
            VerdictLabel.CONTESTED,
            "Reliable evidence exists on both sides, so the claim is contested.",
        )

    if contradiction_score >= thresholds.contradicted_min:
        return (
            VerdictLabel.CONTRADICTED,
            "The claim is contradicted by the available evidence.",
        )

    if support_score >= thresholds.supported_min and contradiction_score < thresholds.low_evidence_max:
        return (
            VerdictLabel.SUPPORTED,
            "The claim is supported by the available evidence.",
        )

    if support_score >= thresholds.partial_min:
        return (
            VerdictLabel.PARTIALLY_SUPPORTED,
            "The claim has partial support, but the evidence is not strong enough for a full supported verdict.",
        )

    if uncertainty_score > 0.75:
        return (
            VerdictLabel.UNVERIFIABLE,
            "There is not enough reliable evidence to verify the claim.",
        )

    return (
        VerdictLabel.UNVERIFIABLE,
        "The available evidence is insufficient for a confident verdict.",
    )


def _calculate_confidence(
    support_score: float,
    contradiction_score: float,
    uncertainty_score: float,
) -> float:
    strongest_signal = max(support_score, contradiction_score)
    conflict_penalty = min(support_score, contradiction_score)
    raw_confidence = strongest_signal - conflict_penalty - (uncertainty_score * 0.2)
    return round(max(0.0, min(1.0, raw_confidence)), 4)
