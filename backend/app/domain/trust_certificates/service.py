import hashlib
from collections import defaultdict
from statistics import mean
from urllib.parse import urlparse

from app.schemas.agent import AtomicClaim, EvidenceItem, PivotVerdict
from app.schemas.evidence_graph import EvidenceGraph
from app.schemas.trust_certificate import (
    TrustCertificate,
    TrustCertificateClaimSummary,
    TrustCertificateEvidenceSummary,
    TrustCertificateIndependenceSummary,
    TrustCertificateLifecycleEvent,
    TrustCertificateSourceSummary,
)


def stable_id(prefix: str, *parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def normalize_domain(url: str | None) -> str | None:
    if not url:
        return None

    parsed = urlparse(url)
    domain = parsed.netloc or parsed.path.split("/", 1)[0]
    domain = domain.lower().strip().removeprefix("www.")

    return domain or None


class TrustCertificateBuilder:
    def build(
        self,
        *,
        case_id: str,
        overall_verdict: str,
        confidence: float,
        claims: list[AtomicClaim],
        evidence_items: list[EvidenceItem],
        verdicts: list[PivotVerdict],
        evidence_graph: EvidenceGraph | None = None,
    ) -> TrustCertificate:
        verdict_by_claim_id = {verdict.claim_id: verdict for verdict in verdicts}

        claim_summaries = [
            self._claim_summary(claim, verdict_by_claim_id.get(claim.claim_id))
            for claim in claims
        ]

        evidence_summaries = [
            self._evidence_summary(evidence)
            for evidence in evidence_items
        ]

        source_summaries = self._source_summaries(evidence_items)
        independence_summaries = self._independence_summaries(evidence_items)

        trust_index = self._trust_index(
            confidence=confidence,
            evidence_items=evidence_items,
            verdicts=verdicts,
        )

        certificate = TrustCertificate(
            certificate_id=stable_id("cert", case_id, overall_verdict, confidence),
            case_id=case_id,
            lifecycle_status="active",
            lifecycle_events=[
                TrustCertificateLifecycleEvent(
                    event_type="issued",
                    status_before=None,
                    status_after="active",
                    reason="Certificate issued after completed investigation.",
                    metadata={
                        "overall_verdict": overall_verdict,
                        "confidence": round(confidence, 4),
                    },
                )
            ],
            overall_verdict=overall_verdict,
            confidence=round(confidence, 4),
            trust_index=trust_index,
            claims=claim_summaries,
            evidence=evidence_summaries,
            sources=source_summaries,
            independence_clusters=independence_summaries,
            evidence_graph_id=evidence_graph.graph_id if evidence_graph else None,
            evidence_graph_summary=evidence_graph.summary if evidence_graph else {},
            summary={
                "claim_count": len(claims),
                "evidence_count": len(evidence_items),
                "source_count": len(source_summaries),
                "independence_cluster_count": len(independence_summaries),
                "verdict_count": len(verdicts),
            },
        )

        return certificate

    def _claim_summary(
        self,
        claim: AtomicClaim,
        verdict: PivotVerdict | None,
    ) -> TrustCertificateClaimSummary:
        return TrustCertificateClaimSummary(
            claim_id=claim.claim_id,
            claim_text=claim.claim_text,
            verdict=(
                getattr(verdict.verdict, "value", str(verdict.verdict))
                if verdict is not None
                else None
            ),
            confidence=verdict.confidence if verdict is not None else None,
            support_score=verdict.support_score if verdict is not None else None,
            contradiction_score=verdict.contradiction_score if verdict is not None else None,
            uncertainty_score=verdict.uncertainty_score if verdict is not None else None,
        )

    def _evidence_summary(
        self,
        evidence: EvidenceItem,
    ) -> TrustCertificateEvidenceSummary:
        return TrustCertificateEvidenceSummary(
            evidence_id=evidence.evidence_id,
            claim_id=evidence.claim_id,
            source_id=evidence.source_id,
            url=evidence.url,
            title=evidence.title,
            reliability=evidence.reliability,
            independence=evidence.independence,
            specificity=evidence.specificity,
            freshness=evidence.freshness,
            independence_group=evidence.independence_group,
        )

    def _source_summaries(
        self,
        evidence_items: list[EvidenceItem],
    ) -> list[TrustCertificateSourceSummary]:
        by_source: dict[str, list[EvidenceItem]] = defaultdict(list)
        for evidence in evidence_items:
            by_source[evidence.source_id].append(evidence)

        summaries: list[TrustCertificateSourceSummary] = []
        for source_id, items in sorted(by_source.items()):
            first = items[0]
            metadata = first.metadata or {}

            summaries.append(
                TrustCertificateSourceSummary(
                    source_id=source_id,
                    domain=metadata.get("reliability_domain") or normalize_domain(first.url),
                    reliability=round(mean(item.reliability for item in items), 4),
                    reliability_source=metadata.get("reliability_source"),
                    independence_group=first.independence_group,
                )
            )

        return summaries

    def _independence_summaries(
        self,
        evidence_items: list[EvidenceItem],
    ) -> list[TrustCertificateIndependenceSummary]:
        by_cluster: dict[str, list[EvidenceItem]] = defaultdict(list)

        for evidence in evidence_items:
            cluster = evidence.independence_group
            if cluster:
                by_cluster[cluster].append(evidence)

        summaries: list[TrustCertificateIndependenceSummary] = []
        for cluster_id, items in sorted(by_cluster.items()):
            discounts = [
                item.metadata.get("corroboration_discount")
                for item in items
                if item.metadata and item.metadata.get("corroboration_discount") is not None
            ]

            summaries.append(
                TrustCertificateIndependenceSummary(
                    cluster_id=cluster_id,
                    evidence_count=len(items),
                    average_independence=round(mean(item.independence for item in items), 4),
                    average_corroboration_discount=(
                        round(mean(float(discount) for discount in discounts), 4)
                        if discounts
                        else None
                    ),
                )
            )

        return summaries

    def _trust_index(
        self,
        *,
        confidence: float,
        evidence_items: list[EvidenceItem],
        verdicts: list[PivotVerdict],
    ) -> float:
        if not evidence_items:
            return round(max(0.0, min(1.0, confidence * 0.5)), 4)

        avg_reliability = mean(evidence.reliability for evidence in evidence_items)
        avg_independence = mean(evidence.independence for evidence in evidence_items)
        avg_specificity = mean(evidence.specificity for evidence in evidence_items)

        score = (
            confidence * 0.45
            + avg_reliability * 0.25
            + avg_independence * 0.15
            + avg_specificity * 0.15
        )

        if any(
            getattr(verdict.verdict, "value", str(verdict.verdict)) == "unverifiable"
            for verdict in verdicts
        ):
            score *= 0.75

        return round(max(0.0, min(1.0, score)), 4)
