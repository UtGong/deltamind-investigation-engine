from dataclasses import dataclass
from urllib.parse import urlparse

from app.schemas.agent import EvidenceItem


@dataclass(frozen=True)
class ReliabilityResolution:
    reliability: float
    source: str
    domain: str | None = None
    topic: str | None = None
    claim_type: str | None = None
    uncertainty: float | None = None
    original_reliability: float | None = None


def normalize_domain(value: str | None) -> str | None:
    if not value:
        return None

    parsed = urlparse(value)
    domain = parsed.netloc or parsed.path.split("/", 1)[0]
    domain = domain.lower().strip().removeprefix("www.")

    if not domain or "." not in domain:
        return None

    return domain


def domain_from_source_id(source_id: str | None) -> str | None:
    if not source_id:
        return None

    value = source_id
    if value.startswith("cached::"):
        value = value.removeprefix("cached::")

    value = value.removeprefix("source_")
    value = value.replace("_", ".")

    return normalize_domain(value)


class SourceReliabilityService:
    def resolve(
        self,
        *,
        url: str | None,
        source_id: str | None,
        claim_type: str = "unknown",
        topic: str | None = None,
        fallback: float = 0.5,
    ) -> ReliabilityResolution:
        domain = normalize_domain(url) or domain_from_source_id(source_id)
        fallback = max(0.0, min(1.0, float(fallback)))

        if domain is None:
            return ReliabilityResolution(
                reliability=fallback,
                source="fallback_no_domain",
                original_reliability=fallback,
            )

        try:
            from app.db.models import SourceRecord, SourceReliabilityRecord
            from app.db.session import SessionLocal

            claim_type_candidates = [claim_type]
            if claim_type != "unknown":
                claim_type_candidates.append("unknown")

            domain_candidates = [domain, f"www.{domain}"]

            with SessionLocal() as session:
                query = (
                    session.query(SourceReliabilityRecord)
                    .filter(SourceReliabilityRecord.domain.in_(domain_candidates))
                    .filter(SourceReliabilityRecord.claim_type.in_(claim_type_candidates))
                )

                records = query.all()

                if topic:
                    exact_topic_records = [record for record in records if record.topic == topic]
                    if exact_topic_records:
                        records = exact_topic_records

                if records:
                    best = sorted(
                        records,
                        key=lambda record: (
                            record.topic == topic,
                            record.claim_type == claim_type,
                            record.num_observations,
                            record.reliability_mean,
                        ),
                        reverse=True,
                    )[0]

                    return ReliabilityResolution(
                        reliability=max(0.0, min(1.0, float(best.reliability_mean))),
                        source="learned_source_reliability",
                        domain=best.domain,
                        topic=best.topic,
                        claim_type=best.claim_type,
                        uncertainty=best.reliability_uncertainty,
                        original_reliability=fallback,
                    )

                source_record = (
                    session.query(SourceRecord)
                    .filter(SourceRecord.domain.in_(domain_candidates))
                    .filter(SourceRecord.reliability_prior.isnot(None))
                    .order_by(SourceRecord.reliability_prior.desc())
                    .first()
                )

                if source_record is not None:
                    return ReliabilityResolution(
                        reliability=max(0.0, min(1.0, float(source_record.reliability_prior))),
                        source="source_record_prior",
                        domain=source_record.domain,
                        topic=topic,
                        claim_type=claim_type,
                        uncertainty=None,
                        original_reliability=fallback,
                    )

        except Exception as exc:
            return ReliabilityResolution(
                reliability=fallback,
                source="fallback_lookup_error",
                domain=domain,
                topic=topic,
                claim_type=claim_type,
                uncertainty=None,
                original_reliability=fallback,
            )

        return ReliabilityResolution(
            reliability=fallback,
            source="fallback_existing_evidence",
            domain=domain,
            topic=topic,
            claim_type=claim_type,
            uncertainty=None,
            original_reliability=fallback,
        )

    def apply_to_evidence_items(
        self,
        *,
        evidence_items: list[EvidenceItem],
        claim_type: str = "unknown",
        topic: str | None = None,
    ) -> list[EvidenceItem]:
        for evidence in evidence_items:
            resolution = self.resolve(
                url=evidence.url,
                source_id=evidence.source_id,
                claim_type=claim_type,
                topic=topic,
                fallback=evidence.reliability,
            )

            evidence.reliability = resolution.reliability

            metadata = dict(evidence.metadata or {})
            metadata["reliability_source"] = resolution.source
            metadata["reliability_original"] = resolution.original_reliability
            metadata["reliability_learned"] = resolution.reliability
            metadata["reliability_domain"] = resolution.domain
            metadata["reliability_topic"] = resolution.topic
            metadata["reliability_claim_type"] = resolution.claim_type
            metadata["reliability_uncertainty"] = resolution.uncertainty
            evidence.metadata = metadata

        return evidence_items
