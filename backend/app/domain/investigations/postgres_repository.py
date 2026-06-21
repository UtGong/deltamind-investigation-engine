import hashlib
from urllib.parse import urlparse

from app.core.constants import SourceType
from app.db.models import (
    CaseRecord as DBCaseRecord,
    ClaimRecord,
    EvidenceRecord,
    SourceRecord,
    StanceRecord,
)
from app.db.session import SessionLocal
from app.domain.investigations.repository import InvestigationRepository
from app.domain.verified_claims.models import normalize_claim_text
from app.schemas.agent import EvidenceItem, PivotVerdict, StanceResult
from app.schemas.api import InvestigationResult


class PostgresInvestigationRepository(InvestigationRepository):
    def save(self, result: InvestigationResult) -> InvestigationResult:
        result_json = result.model_dump(mode="json")

        with SessionLocal() as session:
            case_record = session.get(DBCaseRecord, result.case_id)

            if case_record is None:
                raise ValueError(
                    f"Cannot save investigation result because case does not exist: {result.case_id}"
                )

            case_record.status = result.status.value
            case_record.case_verdict = (
                result.case_verdict.value if result.case_verdict is not None else None
            )
            case_record.confidence = result.confidence
            case_record.investigation_result_json = result_json

            self._replace_materialized_rows(session, result)

            session.commit()

        return result

    def get(self, case_id: str) -> InvestigationResult | None:
        with SessionLocal() as session:
            record = session.get(DBCaseRecord, case_id)

            if record is None or record.investigation_result_json is None:
                return None

            return InvestigationResult.model_validate(
                record.investigation_result_json
            )

    def _replace_materialized_rows(self, session, result: InvestigationResult) -> None:
        session.query(StanceRecord).filter(
            StanceRecord.case_id == result.case_id
        ).delete(synchronize_session=False)

        session.query(EvidenceRecord).filter(
            EvidenceRecord.case_id == result.case_id
        ).delete(synchronize_session=False)

        session.query(ClaimRecord).filter(
            ClaimRecord.case_id == result.case_id
        ).delete(synchronize_session=False)

        verdict_by_claim_id = {
            verdict.claim_id: verdict
            for verdict in result.verdicts
        }

        for claim in result.claims:
            verdict = verdict_by_claim_id.get(claim.claim_id)

            session.merge(
                ClaimRecord(
                    claim_id=claim.claim_id,
                    case_id=result.case_id,
                    claim_text=claim.claim_text,
                    normalized_claim_text=normalize_claim_text(claim.claim_text),
                    claim_type=claim.claim_type.value,
                    subject=claim.subject,
                    predicate=claim.predicate,
                    object_value=claim.object,
                    event_time=claim.event_time,
                    decomposition_confidence=claim.confidence,
                    final_verdict=(
                        verdict.verdict.value if verdict is not None else None
                    ),
                    correctness_score=self._correctness_score_from_verdict(verdict),
                    trust_score=None,
                    uncertainty_score=(
                        verdict.uncertainty_score if verdict is not None else None
                    ),
                    metadata_json={
                        "source": "investigation_result_materialization",
                        "verdict_reason": verdict.reason if verdict is not None else None,
                        "verdict_debug": verdict.debug if verdict is not None else {},
                    },
                )
            )

        source_records_by_id = {}

        for evidence in result.evidence:
            source_record = self._source_record_from_evidence(evidence)
            existing_source_record = source_records_by_id.get(source_record.source_id)

            if existing_source_record is None:
                source_records_by_id[source_record.source_id] = source_record
            else:
                existing_metadata = dict(existing_source_record.metadata_json or {})
                evidence_ids = list(existing_metadata.get("evidence_ids", []))
                evidence_ids.append(evidence.evidence_id)
                existing_metadata["evidence_ids"] = sorted(set(evidence_ids))
                existing_source_record.metadata_json = existing_metadata

                if source_record.reliability_prior is not None:
                    existing_source_record.reliability_prior = max(
                        existing_source_record.reliability_prior or 0.0,
                        source_record.reliability_prior,
                    )

        for source_record in source_records_by_id.values():
            session.merge(source_record)

        for evidence in result.evidence:
            session.merge(self._evidence_record_from_evidence(result.case_id, evidence))

        for stance in result.stances:
            session.merge(self._stance_record_from_stance(result.case_id, stance))

    def _source_record_from_evidence(self, evidence: EvidenceItem) -> SourceRecord:
        domain = None
        if evidence.url:
            parsed = urlparse(evidence.url)
            domain = parsed.netloc or None

        return SourceRecord(
            source_id=evidence.source_id,
            domain=domain,
            source_name=evidence.title,
            source_type=SourceType.UNKNOWN.value,
            url=evidence.url,
            reliability_prior=evidence.reliability,
            metadata_json={
                "source": "investigation_result_materialization",
                "evidence_id": evidence.evidence_id,
                "evidence_ids": [evidence.evidence_id],
                "published_at": (
                    evidence.published_at.isoformat()
                    if evidence.published_at is not None
                    else None
                ),
                "retrieved_at": (
                    evidence.retrieved_at.isoformat()
                    if evidence.retrieved_at is not None
                    else None
                ),
                "author": evidence.author,
            },
        )

    def _evidence_record_from_evidence(
        self,
        case_id: str,
        evidence: EvidenceItem,
    ) -> EvidenceRecord:
        return EvidenceRecord(
            evidence_id=evidence.evidence_id,
            case_id=case_id,
            claim_id=evidence.claim_id,
            source_id=evidence.source_id,
            query_id=None,
            url=evidence.url,
            title=evidence.title,
            evidence_text=evidence.evidence_text,
            evidence_span_start=None,
            evidence_span_end=None,
            retrieval_method="investigation_result",
            source_type=SourceType.UNKNOWN.value,
            independence_group=evidence.independence_group,
            reliability=evidence.reliability,
            independence=evidence.independence,
            freshness=evidence.freshness,
            specificity=evidence.specificity,
            metadata_json={
                "source": "investigation_result_materialization",
                "author": evidence.author,
                "published_at": (
                    evidence.published_at.isoformat()
                    if evidence.published_at is not None
                    else None
                ),
                "retrieved_at": (
                    evidence.retrieved_at.isoformat()
                    if evidence.retrieved_at is not None
                    else None
                ),
            },
        )

    def _stance_record_from_stance(
        self,
        case_id: str,
        stance: StanceResult,
    ) -> StanceRecord:
        return StanceRecord(
            stance_id=self._stance_id(stance),
            case_id=case_id,
            claim_id=stance.claim_id,
            evidence_id=stance.evidence_id,
            stance_label=stance.stance.value,
            confidence=stance.confidence,
            explanation=stance.reason,
            provider=None,
            model=None,
            metadata_json={
                "source": "investigation_result_materialization",
            },
        )

    def _stance_id(self, stance: StanceResult) -> str:
        raw = f"{stance.claim_id}::{stance.evidence_id}::{stance.stance.value}"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
        return f"stance_{digest}"

    def _correctness_score_from_verdict(
        self,
        verdict: PivotVerdict | None,
    ) -> float | None:
        if verdict is None:
            return None

        return verdict.confidence
