from app.core.constants import ClaimType, StanceLabel, VerdictLabel
from app.domain.evidence_graph.service import EvidenceGraphBuilder
from app.domain.trust_certificates.service import TrustCertificateBuilder
from app.schemas.agent import AtomicClaim, EvidenceItem, PivotVerdict, StanceResult


def test_trust_certificate_builder_creates_certificate_summary():
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

    certificate = TrustCertificateBuilder().build(
        case_id="case_1",
        overall_verdict="contradicted",
        confidence=0.69,
        claims=[claim],
        evidence_items=[evidence],
        verdicts=[verdict],
        evidence_graph=graph,
    )

    assert certificate.case_id == "case_1"
    assert certificate.lifecycle_status == "active"
    assert certificate.lifecycle_events[0].event_type == "issued"
    assert certificate.lifecycle_events[0].status_after == "active"
    assert certificate.overall_verdict == "contradicted"
    assert certificate.evidence_graph_id == graph.graph_id
    assert certificate.trust_index > 0.0

    assert certificate.summary["claim_count"] == 1
    assert certificate.summary["evidence_count"] == 1
    assert certificate.summary["source_count"] == 1
    assert certificate.summary["independence_cluster_count"] == 1

    assert certificate.claims[0].verdict == "contradicted"
    assert certificate.sources[0].domain == "nba.com"
    assert certificate.sources[0].reliability_source == "learned_source_reliability"
    assert certificate.independence_clusters[0].cluster_id == "domain:nba.com"
