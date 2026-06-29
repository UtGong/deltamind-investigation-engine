from collections import Counter
from dataclasses import dataclass
from urllib.parse import parse_qsl, unquote_plus, urlparse

from app.schemas.agent import EvidenceItem


@dataclass(frozen=True)
class IndependenceResolution:
    independence: float
    independence_group: str
    source: str
    common_origin_cluster: str
    corroboration_discount: float
    reason: str


def normalize_domain(url: str | None) -> str | None:
    if not url:
        return None

    parsed = urlparse(url)
    domain = parsed.netloc or parsed.path.split("/", 1)[0]
    domain = domain.lower().strip().removeprefix("www.")

    if not domain or "." not in domain:
        return None

    return domain


def normalize_url_for_duplicate_detection(url: str | None) -> str | None:
    if not url:
        return None

    parsed = urlparse(url)
    domain = normalize_domain(url)
    if not domain:
        return None

    path = parsed.path.lower().strip().rstrip("/")

    query_pairs = parse_qsl(parsed.query, keep_blank_values=False)
    normalized_query_parts = [
        f"{key.lower().strip()}={unquote_plus(value).lower().strip()}"
        for key, value in query_pairs
    ]

    normalized_query = "&".join(sorted(normalized_query_parts))
    return f"{domain}{path}?{normalized_query}" if normalized_query else f"{domain}{path}"


def is_search_result_page(url: str | None, title: str | None = None) -> bool:
    parsed = urlparse(url or "")
    text = " ".join([parsed.path.lower(), parsed.query.lower(), (title or "").lower()])

    return any(
        marker in text
        for marker in [
            "/search",
            "search?",
            "search/_/q",
            "query=",
            "q=",
            "search results",
        ]
    )


def is_official_like_domain(domain: str | None) -> bool:
    if not domain:
        return False

    return (
        domain.endswith(".gov")
        or domain.endswith(".edu")
        or domain
        in {
            "nba.com",
            "fifa.com",
            "olympics.com",
            "mlb.com",
            "nfl.com",
            "nhl.com",
        }
    )


class SourceIndependenceService:
    def apply_to_evidence_items(
        self,
        *,
        evidence_items: list[EvidenceItem],
    ) -> list[EvidenceItem]:
        domains = [normalize_domain(evidence.url) or evidence.source_id for evidence in evidence_items]
        normalized_urls = [
            normalize_url_for_duplicate_detection(evidence.url)
            for evidence in evidence_items
        ]

        domain_counts = Counter(domain for domain in domains if domain)
        url_counts = Counter(url for url in normalized_urls if url)

        for evidence, domain, normalized_url in zip(
            evidence_items,
            domains,
            normalized_urls,
        ):
            resolution = self.resolve(
                evidence=evidence,
                domain=str(domain) if domain else None,
                normalized_url=normalized_url,
                domain_count=domain_counts.get(domain, 0) if domain else 0,
                duplicate_url_count=url_counts.get(normalized_url, 0)
                if normalized_url
                else 0,
            )

            evidence.independence = resolution.independence
            evidence.independence_group = resolution.independence_group

            metadata = dict(evidence.metadata or {})
            metadata["independence_source"] = resolution.source
            metadata["common_origin_cluster"] = resolution.common_origin_cluster
            metadata["corroboration_discount"] = resolution.corroboration_discount
            metadata["independence_reason"] = resolution.reason
            metadata["independence_domain"] = domain
            metadata["independence_normalized_url"] = normalized_url
            evidence.metadata = metadata

        return evidence_items

    def resolve(
        self,
        *,
        evidence: EvidenceItem,
        domain: str | None,
        normalized_url: str | None,
        domain_count: int,
        duplicate_url_count: int,
    ) -> IndependenceResolution:
        existing = max(0.0, min(1.0, float(evidence.independence)))

        if domain is None:
            return self._resolution(
                independence=min(existing, 0.5),
                cluster=evidence.source_id or "unknown_source",
                reason="No usable domain was available; used conservative independence.",
            )

        if duplicate_url_count > 1:
            return self._resolution(
                independence=min(existing, 0.25),
                cluster=f"url:{normalized_url or domain}",
                reason="Duplicate normalized URL detected.",
            )

        if domain_count > 1 and is_search_result_page(evidence.url, evidence.title):
            return self._resolution(
                independence=min(existing, 0.35),
                cluster=f"domain:{domain}:search",
                reason="Multiple search-result pages from the same domain were treated as common-origin evidence.",
            )

        if domain_count > 1:
            return self._resolution(
                independence=min(existing, 0.55),
                cluster=f"domain:{domain}",
                reason="Multiple evidence items from the same domain were grouped into one common-origin cluster.",
            )

        if is_official_like_domain(domain):
            return self._resolution(
                independence=max(existing, 0.85),
                cluster=f"domain:{domain}",
                reason="Single official-like source was treated as independently useful evidence.",
            )

        return self._resolution(
            independence=max(existing, 0.75),
            cluster=f"domain:{domain}",
            reason="Single-domain evidence was treated as moderately independent.",
        )

    def _resolution(
        self,
        *,
        independence: float,
        cluster: str,
        reason: str,
    ) -> IndependenceResolution:
        independence = round(max(0.0, min(1.0, independence)), 4)

        return IndependenceResolution(
            independence=independence,
            independence_group=cluster,
            source="common_origin_cluster_v0",
            common_origin_cluster=cluster,
            corroboration_discount=round(1.0 - independence, 4),
            reason=reason,
        )
