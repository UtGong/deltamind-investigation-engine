import re
from dataclasses import dataclass

from app.schemas.agent import AtomicClaim, EvidenceItem


@dataclass(frozen=True)
class EvidenceQualityDecision:
    keep: bool
    quality_score: float
    relevance_score: float
    boilerplate_score: float
    reason: str


_BOILERPLATE_TERMS = {
    "navigation",
    "toggle",
    "home",
    "tickets",
    "schedule",
    "standings",
    "teams",
    "players",
    "stats",
    "store",
    "privacy policy",
    "terms of use",
    "cookie",
    "subscribe",
    "newsletter",
    "sign in",
    "login",
    "advertisement",
    "sponsored",
    "fantasy",
    "draftkings",
    "fanduel",
}

_LOW_INFORMATION_TITLES = {
    "search",
    "search | nba.com",
    "nba on espn - scores, stats and highlights",
}


def evaluate_evidence_quality(
    claim: AtomicClaim,
    evidence: EvidenceItem,
    min_quality_score: float = 0.35,
) -> EvidenceQualityDecision:
    text = _normalize_text(evidence.evidence_text)
    claim_terms = _claim_terms(claim)

    if not text:
        return EvidenceQualityDecision(
            keep=False,
            quality_score=0.0,
            relevance_score=0.0,
            boilerplate_score=1.0,
            reason="Evidence text is empty.",
        )

    relevance_score = _calculate_relevance_score(
        claim_terms=claim_terms,
        evidence_text=text,
    )
    boilerplate_score = _calculate_boilerplate_score(
        title=evidence.title or "",
        evidence_text=text,
    )
    normalized_title = _normalize_text(evidence.title or "")

    if boilerplate_score >= 0.85:
        return EvidenceQualityDecision(
            keep=False,
            quality_score=0.0,
            relevance_score=round(relevance_score, 4),
            boilerplate_score=round(boilerplate_score, 4),
            reason="Evidence appears dominated by boilerplate/navigation text.",
        )

    if "search" in normalized_title and boilerplate_score >= 0.65:
        return EvidenceQualityDecision(
            keep=False,
            quality_score=0.0,
            relevance_score=round(relevance_score, 4),
            boilerplate_score=round(boilerplate_score, 4),
            reason="Search result page appears too boilerplate-heavy.",
        )

    base_quality = (
        evidence.reliability * 0.30
        + evidence.specificity * 0.25
        + relevance_score * 0.35
        + (1.0 - boilerplate_score) * 0.10
    )

    quality_score = max(0.0, min(1.0, base_quality))

    if quality_score < min_quality_score:
        return EvidenceQualityDecision(
            keep=False,
            quality_score=round(quality_score, 4),
            relevance_score=round(relevance_score, 4),
            boilerplate_score=round(boilerplate_score, 4),
            reason="Evidence quality score is below threshold.",
        )

    if boilerplate_score >= 0.80 and relevance_score < 0.45:
        return EvidenceQualityDecision(
            keep=False,
            quality_score=round(quality_score, 4),
            relevance_score=round(relevance_score, 4),
            boilerplate_score=round(boilerplate_score, 4),
            reason="Evidence appears mostly boilerplate/navigation text.",
        )

    if relevance_score < 0.20:
        return EvidenceQualityDecision(
            keep=False,
            quality_score=round(quality_score, 4),
            relevance_score=round(relevance_score, 4),
            boilerplate_score=round(boilerplate_score, 4),
            reason="Evidence has very low lexical overlap with the claim.",
        )

    return EvidenceQualityDecision(
        keep=True,
        quality_score=round(quality_score, 4),
        relevance_score=round(relevance_score, 4),
        boilerplate_score=round(boilerplate_score, 4),
        reason="Evidence passed quality filter.",
    )


def filter_evidence_items(
    claim: AtomicClaim,
    evidence_items: list[EvidenceItem],
    min_quality_score: float = 0.35,
    min_keep_count: int = 1,
) -> tuple[list[EvidenceItem], list[dict]]:
    decisions: list[dict] = []
    kept: list[EvidenceItem] = []

    for evidence in evidence_items:
        decision = evaluate_evidence_quality(
            claim=claim,
            evidence=evidence,
            min_quality_score=min_quality_score,
        )

        decision_record = {
            "evidence_id": evidence.evidence_id,
            "url": evidence.url,
            "title": evidence.title,
            "keep": decision.keep,
            "quality_score": decision.quality_score,
            "relevance_score": decision.relevance_score,
            "boilerplate_score": decision.boilerplate_score,
            "reason": decision.reason,
        }
        decisions.append(decision_record)

        if decision.keep:
            kept.append(_apply_quality_metadata(evidence, decision_record))

    # Safety valve: do not accidentally erase all evidence when retrieval is scarce.
    # Keep the highest-quality candidate, but mark why it survived.
    if not kept and evidence_items and min_keep_count > 0:
        ranked = sorted(
            zip(evidence_items, decisions),
            key=lambda pair: pair[1]["quality_score"],
            reverse=True,
        )
        fallback_evidence, fallback_decision = ranked[0]
        fallback_decision["keep"] = True
        fallback_decision["reason"] = (
            "Kept as best available evidence because all candidates failed filtering."
        )
        kept.append(_apply_quality_metadata(fallback_evidence, fallback_decision))

    return kept, decisions


def _apply_quality_metadata(
    evidence: EvidenceItem,
    decision_record: dict,
) -> EvidenceItem:
    metadata = dict(getattr(evidence, "metadata", {}) or {})
    metadata["evidence_quality"] = decision_record

    # Pydantic v2 model_copy.
    if hasattr(evidence, "model_copy"):
        return evidence.model_copy(update={"metadata": metadata})

    copied = evidence.copy()
    copied.metadata = metadata
    return copied


def _normalize_text(text: str | None) -> str:
    if not text:
        return ""

    return re.sub(r"\s+", " ", text).strip().lower()


def _claim_terms(claim: AtomicClaim) -> set[str]:
    parts = [
        claim.claim_text,
        claim.subject,
        claim.predicate,
        claim.object,
    ]

    tokens: set[str] = set()

    for part in parts:
        if not part:
            continue

        for token in re.findall(r"[a-zA-Z0-9]+", str(part).lower()):
            if len(token) < 3:
                continue
            tokens.add(token)

    return tokens


def _calculate_relevance_score(
    claim_terms: set[str],
    evidence_text: str,
) -> float:
    if not claim_terms:
        return 0.0

    matched = {
        term
        for term in claim_terms
        if term in evidence_text
    }

    return len(matched) / len(claim_terms)


def _calculate_boilerplate_score(
    title: str,
    evidence_text: str,
) -> float:
    normalized_title = _normalize_text(title)

    title_penalty = 0.0
    if normalized_title in _LOW_INFORMATION_TITLES:
        title_penalty = 0.35
    elif "search" in normalized_title:
        title_penalty = 0.25

    boilerplate_hits = sum(
        1
        for term in _BOILERPLATE_TERMS
        if term in evidence_text
    )

    hit_penalty = min(0.55, boilerplate_hits * 0.05)

    token_count = len(evidence_text.split())
    length_penalty = 0.0

    # Very long pages with many menu terms are often broad pages/search pages.
    if token_count > 400 and boilerplate_hits >= 6:
        length_penalty = 0.20

    return max(0.0, min(1.0, title_penalty + hit_penalty + length_penalty))
