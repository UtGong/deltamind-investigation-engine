from app.domain.source_independence.service import SourceIndependenceService
from app.schemas.agent import EvidenceItem


def make_evidence(evidence_id: str, url: str, independence: float = 0.8) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        claim_id="C1",
        source_id=f"source_{evidence_id}",
        url=url,
        title="Evidence",
        evidence_text="The Boston Celtics won the 2024 NBA Finals.",
        reliability=0.8,
        independence=independence,
        freshness=0.8,
        specificity=0.8,
    )


def test_same_domain_search_results_are_discounted():
    evidence = [
        make_evidence(
            "E1",
            "https://www.espn.com/search/_/q/The+Boston+Celtics+won+the+2024+NBA+Finals.",
        ),
        make_evidence(
            "E2",
            "https://www.espn.com/search/_/q/The%20Boston%20Celtics%20won%20the%202024%20NBA%20Finals.",
        ),
    ]

    SourceIndependenceService().apply_to_evidence_items(evidence_items=evidence)

    assert evidence[0].independence == 0.35
    assert evidence[1].independence == 0.35
    assert evidence[0].independence_group == "domain:espn.com:search"
    assert evidence[1].independence_group == "domain:espn.com:search"
    assert evidence[0].metadata["independence_source"] == "common_origin_cluster_v0"


def test_single_official_source_gets_high_independence():
    evidence = [
        make_evidence("E1", "https://www.nba.com/playoffs/2024/nba-finals", 0.5),
    ]

    SourceIndependenceService().apply_to_evidence_items(evidence_items=evidence)

    assert evidence[0].independence == 0.85
    assert evidence[0].independence_group == "domain:nba.com"
    assert evidence[0].metadata["corroboration_discount"] == 0.15


def test_duplicate_url_gets_strong_discount():
    evidence = [
        make_evidence("E1", "https://example.com/article?id=1", 0.8),
        make_evidence("E2", "https://www.example.com/article?id=1", 0.8),
    ]

    SourceIndependenceService().apply_to_evidence_items(evidence_items=evidence)

    assert evidence[0].independence == 0.25
    assert evidence[1].independence == 0.25
    assert evidence[0].independence_group == evidence[1].independence_group
