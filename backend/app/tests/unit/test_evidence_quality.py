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
            title="Short local report",
            evidence_text="A brief local sports note with limited details.",
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


def test_filter_does_not_keep_query_echo_search_page_as_best_available():
    claim = AtomicClaim(
        claim_id="C1",
        claim_text="Belgium won the match with a score of 3-1.",
        claim_type=ClaimType.RESULT,
        subject="Belgium",
        predicate="won",
        object="score of 3-1",
    )

    evidence = [
        EvidenceItem(
            evidence_id="E1",
            claim_id="C1",
            source_id="source_espn_com",
            url="https://www.espn.com/search?q=Belgium+won+the+match+with+a+score+of+3-1",
            title="Belgium+won+the+match+with+a+score+of+3-1 - ESPN Search",
            evidence_text=(
                "Belgium+won+the+match+with+a+score+of+3-1 - ESPN Search "
                "Skip to main content Skip to navigation ESPN NFL NBA MLB NHL "
                "Terms of Use Privacy Policy Found results for Belgium won the match."
            ),
            reliability=0.9,
            specificity=0.7,
            independence=0.7,
            freshness=0.6,
        )
    ]

    kept, decisions = filter_evidence_items(claim, evidence)

    assert kept == []
    assert decisions[0]["keep"] is False
    assert decisions[0]["unsafe_to_keep"] is True
    assert "low-value" in decisions[0]["reason"]
