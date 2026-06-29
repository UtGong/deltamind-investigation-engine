import hashlib
from collections import Counter
from typing import Iterable

from app.schemas.agent import AtomicClaim, EvidenceItem, PivotVerdict, StanceResult
from app.schemas.evidence_graph import (
    EvidenceGraph,
    EvidenceGraphEdge,
    EvidenceGraphNode,
)


def stable_id(prefix: str, *parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


class EvidenceGraphBuilder:
    def build(
        self,
        *,
        case_id: str,
        claims: list[AtomicClaim],
        evidence_items: list[EvidenceItem],
        stance_results: list[StanceResult],
        verdicts: list[PivotVerdict],
    ) -> EvidenceGraph:
        graph = EvidenceGraph(
            graph_id=stable_id("graph", case_id),
            case_id=case_id,
        )

        node_ids: set[str] = set()
        edge_ids: set[str] = set()

        def add_node(node: EvidenceGraphNode) -> None:
            if node.node_id not in node_ids:
                graph.nodes.append(node)
                node_ids.add(node.node_id)

        def add_edge(edge: EvidenceGraphEdge) -> None:
            if edge.edge_id not in edge_ids:
                graph.edges.append(edge)
                edge_ids.add(edge.edge_id)

        claims_by_id = {claim.claim_id: claim for claim in claims}
        evidence_by_id = {evidence.evidence_id: evidence for evidence in evidence_items}
        verdicts_by_claim_id = {verdict.claim_id: verdict for verdict in verdicts}

        for claim in claims:
            claim_node_id = self._claim_node_id(claim.claim_id)
            add_node(
                EvidenceGraphNode(
                    node_id=claim_node_id,
                    node_type="claim",
                    label=claim.claim_text,
                    data={
                        "claim_id": claim.claim_id,
                        "claim_text": claim.claim_text,
                        "claim_type": getattr(claim.claim_type, "value", str(claim.claim_type)),
                        "subject": claim.subject,
                        "predicate": claim.predicate,
                        "object": claim.object,
                        "confidence": claim.confidence,
                    },
                )
            )

            verdict = verdicts_by_claim_id.get(claim.claim_id)
            if verdict is not None:
                verdict_node_id = self._verdict_node_id(verdict.claim_id)
                add_node(
                    EvidenceGraphNode(
                        node_id=verdict_node_id,
                        node_type="verdict",
                        label=getattr(verdict.verdict, "value", str(verdict.verdict)),
                        data=verdict.model_dump(mode="json"),
                    )
                )
                add_edge(
                    EvidenceGraphEdge(
                        edge_id=stable_id("edge", claim_node_id, "has_verdict", verdict_node_id),
                        edge_type="has_verdict",
                        source_node_id=claim_node_id,
                        target_node_id=verdict_node_id,
                        label="has verdict",
                        data={
                            "confidence": verdict.confidence,
                            "support_score": verdict.support_score,
                            "contradiction_score": verdict.contradiction_score,
                            "uncertainty_score": verdict.uncertainty_score,
                        },
                    )
                )

        for evidence in evidence_items:
            evidence_node_id = self._evidence_node_id(evidence.evidence_id)
            claim_node_id = self._claim_node_id(evidence.claim_id)
            source_node_id = self._source_node_id(evidence.source_id)

            add_node(
                EvidenceGraphNode(
                    node_id=evidence_node_id,
                    node_type="evidence",
                    label=evidence.title or evidence.url or evidence.evidence_id,
                    data=evidence.model_dump(mode="json"),
                )
            )

            add_node(
                EvidenceGraphNode(
                    node_id=source_node_id,
                    node_type="source",
                    label=evidence.source_id,
                    data={
                        "source_id": evidence.source_id,
                        "url": evidence.url,
                        "reliability": evidence.reliability,
                        "reliability_source": (evidence.metadata or {}).get("reliability_source"),
                        "reliability_domain": (evidence.metadata or {}).get("reliability_domain"),
                    },
                )
            )

            if evidence.claim_id in claims_by_id:
                add_edge(
                    EvidenceGraphEdge(
                        edge_id=stable_id("edge", claim_node_id, "has_evidence", evidence_node_id),
                        edge_type="has_evidence",
                        source_node_id=claim_node_id,
                        target_node_id=evidence_node_id,
                        label="has evidence",
                        data={
                            "specificity": evidence.specificity,
                            "freshness": evidence.freshness,
                            "independence": evidence.independence,
                            "reliability": evidence.reliability,
                        },
                    )
                )

            add_edge(
                EvidenceGraphEdge(
                    edge_id=stable_id("edge", evidence_node_id, "from_source", source_node_id),
                    edge_type="from_source",
                    source_node_id=evidence_node_id,
                    target_node_id=source_node_id,
                    label="from source",
                    data={
                        "url": evidence.url,
                        "source_id": evidence.source_id,
                    },
                )
            )

            cluster = evidence.independence_group or (evidence.metadata or {}).get("common_origin_cluster")
            if cluster:
                cluster_node_id = self._cluster_node_id(cluster)
                add_node(
                    EvidenceGraphNode(
                        node_id=cluster_node_id,
                        node_type="independence_cluster",
                        label=cluster,
                        data={
                            "cluster": cluster,
                            "independence_source": (evidence.metadata or {}).get("independence_source"),
                            "corroboration_discount": (evidence.metadata or {}).get("corroboration_discount"),
                            "reason": (evidence.metadata or {}).get("independence_reason"),
                        },
                    )
                )
                add_edge(
                    EvidenceGraphEdge(
                        edge_id=stable_id("edge", evidence_node_id, "belongs_to_cluster", cluster_node_id),
                        edge_type="belongs_to_cluster",
                        source_node_id=evidence_node_id,
                        target_node_id=cluster_node_id,
                        label="belongs to common-origin cluster",
                        data={
                            "independence": evidence.independence,
                            "corroboration_discount": (evidence.metadata or {}).get("corroboration_discount"),
                        },
                    )
                )

        for stance in stance_results:
            evidence = evidence_by_id.get(stance.evidence_id)
            if evidence is None:
                continue

            claim_node_id = self._claim_node_id(stance.claim_id)
            evidence_node_id = self._evidence_node_id(stance.evidence_id)

            add_edge(
                EvidenceGraphEdge(
                    edge_id=stable_id("edge", evidence_node_id, "has_stance", claim_node_id, stance.stance),
                    edge_type="has_stance",
                    source_node_id=evidence_node_id,
                    target_node_id=claim_node_id,
                    label=getattr(stance.stance, "value", str(stance.stance)),
                    data=stance.model_dump(mode="json"),
                )
            )

        graph.summary = self._summary(
            claims=claims,
            evidence_items=evidence_items,
            stance_results=stance_results,
            verdicts=verdicts,
            nodes=graph.nodes,
            edges=graph.edges,
        )

        return graph

    def _summary(
        self,
        *,
        claims: list[AtomicClaim],
        evidence_items: list[EvidenceItem],
        stance_results: list[StanceResult],
        verdicts: list[PivotVerdict],
        nodes: Iterable[EvidenceGraphNode],
        edges: Iterable[EvidenceGraphEdge],
    ) -> dict:
        node_counts = Counter(node.node_type for node in nodes)
        edge_counts = Counter(edge.edge_type for edge in edges)
        verdict_counts = Counter(
            getattr(verdict.verdict, "value", str(verdict.verdict))
            for verdict in verdicts
        )
        cluster_counts = Counter(
            evidence.independence_group
            for evidence in evidence_items
            if evidence.independence_group
        )

        return {
            "claim_count": len(claims),
            "evidence_count": len(evidence_items),
            "stance_count": len(stance_results),
            "verdict_count": len(verdicts),
            "node_counts": dict(node_counts),
            "edge_counts": dict(edge_counts),
            "verdict_counts": dict(verdict_counts),
            "independence_cluster_counts": dict(cluster_counts),
        }

    def _claim_node_id(self, claim_id: str) -> str:
        return f"claim:{claim_id}"

    def _evidence_node_id(self, evidence_id: str) -> str:
        return f"evidence:{evidence_id}"

    def _source_node_id(self, source_id: str) -> str:
        return f"source:{source_id}"

    def _verdict_node_id(self, claim_id: str) -> str:
        return f"verdict:{claim_id}"

    def _cluster_node_id(self, cluster: str) -> str:
        return f"cluster:{cluster}"
