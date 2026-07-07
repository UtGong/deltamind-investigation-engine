from app.algorithm.pivot.evidence_quality import (
    evaluate_evidence_quality,
    filter_evidence_items,
)
from app.core.constants import ClaimType
from app.schemas.agent import AtomicClaim, EvidenceItem


def test_evidence_quality_keeps_relevant_direct_evidence():
    claim = AtomicClaim(
        claim_id="C1",
        claim_text="The Team Green won the 2024 Example Final.",
        claim_type=ClaimType.EVENT,
        subject="Team Green",
        predicate="won",
        object="2024 Example Final",
    )

    evidence = EvidenceItem(
        evidence_id="E1",
        claim_id="C1",
        source_id="S1",
        url="https://www.example.org/news/example",
        title="Team Green win 2024 Example Final",
        evidence_text="The Team Green won the 2024 Example Final after defeating the Team Silver.",
        reliability=0.95,
        specificity=0.9,
        independence=0.7,
        freshness=0.7,
    )

    decision = evaluate_evidence_quality(claim, evidence)

    assert decision.keep is True
    assert decision.relevance_score >= 0.5
    assert decision.quality_score >= 0.5


def test_evidence_quality_flags_navigation_search_page():
    claim = AtomicClaim(
        claim_id="C1",
        claim_text="The Team Green won the 2024 Example Final.",
        claim_type=ClaimType.EVENT,
        subject="Team Green",
        predicate="won",
        object="2024 Example Final",
    )

    evidence = EvidenceItem(
        evidence_id="E1",
        claim_id="C1",
        source_id="S1",
        url="https://www.example.org/search?query=Boston+Team Green",
        title="Search | Example League.com",
        evidence_text=(
            "Navigation Toggle Home Tickets Example Schedule Standings Teams Players Stats "
            "Store Fantasy DraftKings FanDuel Privacy Policy Terms of Use Subscribe Login "
            "Team Green Example Final"
        ),
        reliability=0.95,
        specificity=0.4,
        independence=0.7,
        freshness=0.6,
    )

    decision = evaluate_evidence_quality(claim, evidence)

    assert decision.keep is False
    assert decision.boilerplate_score >= 0.5


def test_filter_keeps_best_available_when_all_candidates_are_weak():
    claim = AtomicClaim(
        claim_id="C1",
        claim_text="The Team Green won the 2024 Example Final.",
        claim_type=ClaimType.EVENT,
    )

    evidence = [
        EvidenceItem(
            evidence_id="E1",
            claim_id="C1",
            source_id="S1",
            title="Search | Example League.com",
            evidence_text="Navigation Home Tickets Schedule Teams Players Stats Store",
            reliability=0.7,
            specificity=0.2,
            independence=0.5,
            freshness=0.5,
        )
    ]

    kept, decisions = filter_evidence_items(claim, evidence)

    assert len(kept) == 1
    assert len(decisions) == 1
    assert decisions[0]["keep"] is True
    assert "best available evidence" in decisions[0]["reason"]
