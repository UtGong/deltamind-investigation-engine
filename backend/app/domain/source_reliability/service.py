from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import math
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.core.constants import StanceLabel, VerdictLabel
from app.schemas.agent import EvidenceItem
from app.schemas.api import InvestigationResult


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

    def observe_investigation_result(
        self,
        *,
        result: InvestigationResult,
        session: Session | None = None,
    ) -> None:
        close_session = False

        if session is None:
            from app.db.session import SessionLocal

            session = SessionLocal()
            close_session = True

        try:
            self._observe_investigation_result(result=result, session=session)
            if close_session:
                session.commit()
        finally:
            if close_session:
                session.close()

    def _observe_investigation_result(
        self,
        *,
        result: InvestigationResult,
        session: Session,
    ) -> None:
        from app.db.models import SourceRecord, SourceReliabilityRecord

        claims_by_id = {claim.claim_id: claim for claim in result.claims}
        evidence_by_id = {evidence.evidence_id: evidence for evidence in result.evidence}
        verdicts_by_claim_id = {verdict.claim_id: verdict for verdict in result.verdicts}
        now = datetime.now(timezone.utc)

        observations: dict[tuple[str, str, str], list[dict]] = {}

        for stance in result.stances:
            evidence = evidence_by_id.get(stance.evidence_id)
            verdict = verdicts_by_claim_id.get(stance.claim_id)
            claim = claims_by_id.get(stance.claim_id)

            if evidence is None or verdict is None or claim is None:
                continue

            domain = normalize_domain(evidence.url) or domain_from_source_id(evidence.source_id)
            if domain is None:
                continue

            claim_type = claim.claim_type.value
            topic = self._topic_for_claim(claim)
            score = self._observation_score(
                stance_label=stance.stance,
                verdict_label=verdict.verdict,
                stance_confidence=stance.confidence,
                evidence_reliability=evidence.reliability,
                evidence_specificity=evidence.specificity,
            )

            observations.setdefault((domain, claim_type, topic), []).append(
                {
                    "case_id": result.case_id,
                    "claim_id": claim.claim_id,
                    "evidence_id": evidence.evidence_id,
                    "stance": stance.stance.value,
                    "verdict": verdict.verdict.value,
                    "score": score,
                    "stance_confidence": stance.confidence,
                    "evidence_reliability": evidence.reliability,
                    "evidence_specificity": evidence.specificity,
                }
            )

        for (domain, claim_type, topic), items in observations.items():
            if not items:
                continue

            batch_mean = sum(item["score"] for item in items) / len(items)
            record_id = self._reliability_id(domain, claim_type, topic)
            record = session.get(SourceReliabilityRecord, record_id)

            if record is None:
                record = SourceReliabilityRecord(
                    reliability_id=record_id,
                    domain=domain,
                    claim_type=claim_type,
                    topic=topic,
                    reliability_mean=batch_mean,
                    reliability_uncertainty=self._uncertainty(len(items)),
                    num_observations=len(items),
                    last_observed_at=now,
                    metadata_json={
                        "source": "runtime_investigation_learning_v1",
                        "recent_observations": items[-5:],
                    },
                )
                session.add(record)
            else:
                previous_count = int(record.num_observations or 0)
                new_count = previous_count + len(items)
                record.reliability_mean = (
                    (float(record.reliability_mean) * previous_count)
                    + (batch_mean * len(items))
                ) / max(new_count, 1)
                record.reliability_uncertainty = self._uncertainty(new_count)
                record.num_observations = new_count
                record.last_observed_at = now

                metadata = dict(record.metadata_json or {})
                recent = list(metadata.get("recent_observations", []))
                recent.extend(items)
                metadata["source"] = "runtime_investigation_learning_v1"
                metadata["recent_observations"] = recent[-10:]
                record.metadata_json = metadata

            sources = (
                session.query(SourceRecord)
                .filter(SourceRecord.domain.in_([domain, f"www.{domain}"]))
                .all()
            )

            for source in sources:
                source.reliability_prior = max(
                    float(source.reliability_prior or 0.0),
                    float(record.reliability_mean),
                )
                metadata = dict(source.metadata_json or {})
                metadata["runtime_reliability_learning"] = {
                    "source": "runtime_investigation_learning_v1",
                    "claim_type": claim_type,
                    "topic": topic,
                    "reliability_mean": record.reliability_mean,
                    "reliability_uncertainty": record.reliability_uncertainty,
                    "num_observations": record.num_observations,
                    "updated_at": now.isoformat(),
                }
                source.metadata_json = metadata

    def _topic_for_claim(self, claim) -> str:
        claim_text = claim.claim_text.lower()

        if "world cup" in claim_text or "round of 16" in claim_text:
            return "FIFA World Cup"

        if claim.subject:
            return str(claim.subject)[:160]

        return "general"

    def _observation_score(
        self,
        *,
        stance_label: StanceLabel,
        verdict_label: VerdictLabel,
        stance_confidence: float,
        evidence_reliability: float,
        evidence_specificity: float,
    ) -> float:
        alignment = self._stance_verdict_alignment(stance_label, verdict_label)
        evidence_quality = (float(evidence_reliability) + float(evidence_specificity)) / 2
        confidence = max(0.0, min(1.0, float(stance_confidence)))
        score = (0.65 * alignment * confidence) + (0.35 * evidence_quality)
        return max(0.0, min(1.0, score))

    def _stance_verdict_alignment(
        self,
        stance_label: StanceLabel,
        verdict_label: VerdictLabel,
    ) -> float:
        if verdict_label == VerdictLabel.SUPPORTED:
            return {
                StanceLabel.SUPPORTS: 1.0,
                StanceLabel.PARTIALLY_SUPPORTS: 0.75,
                StanceLabel.INSUFFICIENT: 0.25,
                StanceLabel.IRRELEVANT: 0.15,
                StanceLabel.CONTRADICTS: 0.0,
            }.get(stance_label, 0.25)

        if verdict_label == VerdictLabel.CONTRADICTED:
            return {
                StanceLabel.CONTRADICTS: 1.0,
                StanceLabel.PARTIALLY_SUPPORTS: 0.45,
                StanceLabel.INSUFFICIENT: 0.25,
                StanceLabel.IRRELEVANT: 0.15,
                StanceLabel.SUPPORTS: 0.0,
            }.get(stance_label, 0.25)

        if verdict_label == VerdictLabel.UNVERIFIABLE:
            return {
                StanceLabel.INSUFFICIENT: 0.65,
                StanceLabel.IRRELEVANT: 0.5,
                StanceLabel.PARTIALLY_SUPPORTS: 0.35,
                StanceLabel.SUPPORTS: 0.25,
                StanceLabel.CONTRADICTS: 0.25,
            }.get(stance_label, 0.35)

        return {
            StanceLabel.PARTIALLY_SUPPORTS: 0.7,
            StanceLabel.SUPPORTS: 0.55,
            StanceLabel.CONTRADICTS: 0.55,
            StanceLabel.INSUFFICIENT: 0.35,
            StanceLabel.IRRELEVANT: 0.2,
        }.get(stance_label, 0.35)

    def _uncertainty(self, observation_count: int) -> float:
        return max(0.05, min(1.0, 1 / math.sqrt(max(observation_count, 1))))

    def _reliability_id(self, domain: str, claim_type: str, topic: str) -> str:
        digest = hashlib.sha1(f"{domain}|{claim_type}|{topic}".encode("utf-8")).hexdigest()[:16]
        return f"src_rel_{digest}"
