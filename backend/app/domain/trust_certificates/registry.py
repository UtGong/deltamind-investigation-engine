from app.db.models import CaseRecord
from app.db.session import SessionLocal
from app.schemas.trust_certificate import TrustCertificateRegistryItem


class TrustCertificateRegistry:
    def list_recent(self, *, limit: int = 20) -> list[TrustCertificateRegistryItem]:
        limit = max(1, min(limit, 100))

        with SessionLocal() as session:
            rows = (
                session.query(CaseRecord)
                .filter(CaseRecord.investigation_result_json.isnot(None))
                .order_by(CaseRecord.updated_at.desc())
                .limit(limit * 3)
                .all()
            )

        items: list[TrustCertificateRegistryItem] = []

        for row in rows:
            result = row.investigation_result_json or {}
            certificate = result.get("trust_certificate")

            if not certificate:
                continue

            summary = certificate.get("summary") or {}

            items.append(
                TrustCertificateRegistryItem(
                    certificate_id=certificate["certificate_id"],
                    case_id=certificate["case_id"],
                    lifecycle_status=certificate.get("lifecycle_status", "draft"),
                    overall_verdict=certificate.get("overall_verdict"),
                    confidence=certificate.get("confidence", 0.0),
                    trust_index=certificate.get("trust_index", 0.0),
                    issued_at=certificate.get("issued_at"),
                    updated_at=certificate.get("updated_at"),
                    claim_count=summary.get("claim_count", 0),
                    evidence_count=summary.get("evidence_count", 0),
                    source_count=summary.get("source_count", 0),
                    independence_cluster_count=summary.get("independence_cluster_count", 0),
                )
            )

            if len(items) >= limit:
                break

        return items


trust_certificate_registry = TrustCertificateRegistry()
