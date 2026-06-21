from sqlalchemy import select

from app.db.models import CaseRecord as DBCaseRecord
from app.db.session import SessionLocal
from app.domain.cases.models import CaseRecord
from app.domain.cases.repository import CaseRepository


class PostgresCaseRepository(CaseRepository):
    def create(self, case: CaseRecord) -> CaseRecord:
        record = self._db_record_from_domain(case)

        with SessionLocal() as session:
            session.merge(record)
            session.commit()

        return case

    def get(self, case_id: str) -> CaseRecord | None:
        with SessionLocal() as session:
            record = session.get(DBCaseRecord, case_id)

            if record is None:
                return None

            return self._domain_from_db_record(record)

    def update(self, case: CaseRecord) -> CaseRecord:
        record = self._db_record_from_domain(case)

        with SessionLocal() as session:
            existing = session.get(DBCaseRecord, case.case_id)

            if existing is not None:
                record.created_at = existing.created_at
                record.investigation_result_json = existing.investigation_result_json
                record.confidence = existing.confidence
                record.case_verdict = existing.case_verdict

            session.merge(record)
            session.commit()

        return case

    def list(self) -> list[CaseRecord]:
        with SessionLocal() as session:
            records = (
                session.execute(
                    select(DBCaseRecord).order_by(DBCaseRecord.created_at.desc())
                )
                .scalars()
                .all()
            )

        return [self._domain_from_db_record(record) for record in records]

    def _db_record_from_domain(self, case: CaseRecord) -> DBCaseRecord:
        input_url = None

        if case.input_type.value == "url":
            input_url = case.input_text

        return DBCaseRecord(
            case_id=case.case_id,
            input_type=case.input_type.value,
            input_text=case.input_text,
            input_url=input_url,
            title=case.title,
            status=case.status.value,
            case_verdict=None,
            metadata_json={},
            created_at=case.created_at,
            updated_at=case.updated_at,
        )

    def _domain_from_db_record(self, record: DBCaseRecord) -> CaseRecord:
        return CaseRecord(
            case_id=record.case_id,
            input_type=record.input_type,
            input_text=record.input_text or record.input_url or "",
            title=record.title,
            status=record.status,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
