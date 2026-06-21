from sqlalchemy import select

from app.core.constants import AgentRunStatus, CostType
from app.db.models import AgentRunRecord, CostLogRecord
from app.db.session import SessionLocal
from app.domain.audit.repository import AuditRepository
from app.schemas.audit import AgentRun, AuditTrail, CostLog


class PostgresAuditRepository(AuditRepository):
    def add_agent_run(self, agent_run: AgentRun) -> AgentRun:
        metadata = dict(agent_run.metadata or {})

        # AgentRunRecord currently has no dedicated model/input_summary/hash columns.
        # Store those existing API fields losslessly in JSONB.
        if agent_run.model is not None:
            metadata["_audit_model"] = agent_run.model

        record = AgentRunRecord(
            run_id=agent_run.agent_run_id,
            case_id=agent_run.case_id,
            agent_name=agent_run.agent_name,
            provider=agent_run.provider,
            status=agent_run.status.value,
            started_at=agent_run.started_at,
            completed_at=agent_run.completed_at,
            input_json={
                "summary": agent_run.input_summary,
                "hash": agent_run.input_hash,
            },
            output_json={
                "summary": agent_run.output_summary,
                "hash": agent_run.output_hash,
            },
            metadata_json=metadata,
            error_message=None,
        )

        with SessionLocal() as session:
            session.merge(record)
            session.commit()

        return agent_run

    def add_cost_log(self, cost_log: CostLog) -> CostLog:
        record = CostLogRecord(
            cost_id=cost_log.cost_id,
            case_id=cost_log.case_id,
            cost_type=cost_log.cost_type.value,
            provider=cost_log.provider,
            units=cost_log.units,
            unit_name=cost_log.unit_name,
            estimated_cost_usd=cost_log.estimated_cost_usd,
            metadata_json=cost_log.metadata or {},
        )

        with SessionLocal() as session:
            session.merge(record)
            session.commit()

        return cost_log

    def get_trail(self, case_id: str) -> AuditTrail:
        with SessionLocal() as session:
            agent_run_records = (
                session.execute(
                    select(AgentRunRecord)
                    .where(AgentRunRecord.case_id == case_id)
                    .order_by(
                        AgentRunRecord.started_at.asc(),
                        AgentRunRecord.created_at.asc(),
                    )
                )
                .scalars()
                .all()
            )

            cost_log_records = (
                session.execute(
                    select(CostLogRecord)
                    .where(CostLogRecord.case_id == case_id)
                    .order_by(CostLogRecord.created_at.asc())
                )
                .scalars()
                .all()
            )

        return AuditTrail(
            case_id=case_id,
            agent_runs=[
                self._agent_run_from_record(record)
                for record in agent_run_records
            ],
            cost_logs=[
                self._cost_log_from_record(record)
                for record in cost_log_records
            ],
        )

    def clear_case(self, case_id: str) -> None:
        with SessionLocal() as session:
            session.query(AgentRunRecord).filter(
                AgentRunRecord.case_id == case_id
            ).delete()
            session.query(CostLogRecord).filter(
                CostLogRecord.case_id == case_id
            ).delete()
            session.commit()

    def clear_all(self) -> None:
        with SessionLocal() as session:
            session.query(AgentRunRecord).delete()
            session.query(CostLogRecord).delete()
            session.commit()

    def _agent_run_from_record(self, record: AgentRunRecord) -> AgentRun:
        metadata = dict(record.metadata_json or {})
        model = metadata.pop("_audit_model", None)

        input_json = record.input_json or {}
        output_json = record.output_json or {}

        return AgentRun(
            agent_run_id=record.run_id,
            case_id=record.case_id,
            agent_name=record.agent_name,
            status=AgentRunStatus(record.status),
            provider=record.provider or "internal",
            model=model,
            started_at=record.started_at,
            completed_at=record.completed_at,
            input_summary=input_json.get("summary"),
            output_summary=output_json.get("summary"),
            input_hash=input_json.get("hash"),
            output_hash=output_json.get("hash"),
            metadata=metadata,
        )

    def _cost_log_from_record(self, record: CostLogRecord) -> CostLog:
        return CostLog(
            cost_id=record.cost_id,
            case_id=record.case_id,
            cost_type=CostType(record.cost_type),
            provider=record.provider or "internal",
            units=record.units,
            unit_name=record.unit_name or "unit",
            estimated_cost_usd=record.estimated_cost_usd,
            metadata=record.metadata_json or {},
        )
