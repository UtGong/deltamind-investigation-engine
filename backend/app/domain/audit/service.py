import hashlib
import json
from typing import Any
from uuid import uuid4

from app.core.constants import AgentRunStatus, CostType
from app.domain.audit.repository import AuditRepository, audit_repository
from app.domain.cases.models import utc_now
from app.schemas.audit import AgentRun, AuditTrail, CostLog


class AuditService:
    def __init__(self, repository: AuditRepository) -> None:
        self.repository = repository

    def record_agent_run(
        self,
        *,
        case_id: str,
        agent_name: str,
        provider: str = "internal",
        model: str | None = None,
        input_data: Any | None = None,
        output_data: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentRun:
        now = utc_now()

        agent_run = AgentRun(
            agent_run_id=f"run_{uuid4().hex}",
            case_id=case_id,
            agent_name=agent_name,
            status=AgentRunStatus.COMPLETED,
            provider=provider,
            model=model,
            started_at=now,
            completed_at=now,
            input_summary=self._summarize(input_data),
            output_summary=self._summarize(output_data),
            input_hash=self._hash(input_data),
            output_hash=self._hash(output_data),
            metadata=metadata or {},
        )

        return self.repository.add_agent_run(agent_run)

    def record_cost(
        self,
        *,
        case_id: str,
        cost_type: CostType,
        provider: str = "internal",
        units: float = 0.0,
        unit_name: str = "unit",
        estimated_cost_usd: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> CostLog:
        cost_log = CostLog(
            cost_id=f"cost_{uuid4().hex}",
            case_id=case_id,
            cost_type=cost_type,
            provider=provider,
            units=units,
            unit_name=unit_name,
            estimated_cost_usd=estimated_cost_usd,
            metadata=metadata or {},
        )

        return self.repository.add_cost_log(cost_log)

    def get_trail(self, case_id: str) -> AuditTrail:
        return self.repository.get_trail(case_id)

    def _hash(self, data: Any | None) -> str | None:
        if data is None:
            return None

        serialized = self._serialize(data)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _summarize(self, data: Any | None) -> str | None:
        if data is None:
            return None

        serialized = self._serialize(data)
        if len(serialized) <= 300:
            return serialized

        return f"{serialized[:297]}..."

    def _serialize(self, data: Any) -> str:
        if hasattr(data, "model_dump"):
            data = data.model_dump(mode="json")

        return json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)


audit_service = AuditService(audit_repository)
