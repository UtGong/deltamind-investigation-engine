from app.core.constants import ClaimType, StanceLabel, VerdictLabel
from app.domain.evidence_graph.service import EvidenceGraphBuilder
from app.schemas.agent import AtomicClaim, EvidenceItem, PivotVerdict, StanceResult


def test_evidence_graph_builder_creates_core_nodes_and_edges():
    claim = AtomicClaim(
        claim_id="C1",
        claim_text="The Dallas Mavericks won the 2024 NBA Finals.",
        claim_type=ClaimType.UNKNOWN,
        confidence=0.9,
    )
    evidence = EvidenceItem(
        evidence_id="E1",
        claim_id="C1",
        source_id="source_nba",
        url="https://www.nba.com/playoffs/2024/nba-finals",
        title="2024 NBA Finals",
        evidence_text="The Boston Celtics defeated the Dallas Mavericks.",
        reliability=0.8077,
        independence=0.85,
        independence_group="domain:nba.com",
        freshness=0.8,
        specificity=0.9,
        metadata={
            "reliability_source": "learned_source_reliability",
            "reliability_domain": "nba.com",
            "independence_source": "common_origin_cluster_v0",
            "corroboration_discount": 0.15,
        },
    )
    stance = StanceResult(
        claim_id="C1",
        evidence_id="E1",
        stance=StanceLabel.CONTRADICTS,
        confidence=0.95,
        reason="The evidence says Boston won, not Dallas.",
    )
    verdict = PivotVerdict(
        claim_id="C1",
        verdict=VerdictLabel.CONTRADICTED,
        confidence=0.69,
        support_score=0.0,
        contradiction_score=0.69,
        uncertainty_score=0.0,
        reason="Contradictory official evidence.",
    )

    graph = EvidenceGraphBuilder().build(
        case_id="case_1",
        claims=[claim],
        evidence_items=[evidence],
        stance_results=[stance],
        verdicts=[verdict],
    )

    node_types = {node.node_type for node in graph.nodes}
    edge_types = {edge.edge_type for edge in graph.edges}

    assert "claim" in node_types
    assert "evidence" in node_types
    assert "source" in node_types
    assert "verdict" in node_types
    assert "independence_cluster" in node_types

    assert "has_evidence" in edge_types
    assert "from_source" in edge_types
    assert "has_stance" in edge_types
    assert "has_verdict" in edge_types
    assert "belongs_to_cluster" in edge_types

    assert graph.summary["claim_count"] == 1
    assert graph.summary["evidence_count"] == 1
    assert graph.summary["independence_cluster_counts"]["domain:nba.com"] == 1
