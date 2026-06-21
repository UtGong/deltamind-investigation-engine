from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.constants import AgentRunStatus, CostType
from app.domain.cases.models import utc_now


class AgentRun(BaseModel):
    agent_run_id: str
    case_id: str
    agent_name: str

    status: AgentRunStatus = AgentRunStatus.COMPLETED
    provider: str = "internal"
    model: str | None = None

    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None

    input_summary: str | None = None
    output_summary: str | None = None

    input_hash: str | None = None
    output_hash: str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)


class CostLog(BaseModel):
    cost_id: str
    case_id: str
    cost_type: CostType

    provider: str = "internal"
    units: float = 0.0
    unit_name: str = "unit"
    estimated_cost_usd: float = 0.0

    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditTrail(BaseModel):
    case_id: str
    agent_runs: list[AgentRun] = Field(default_factory=list)
    cost_logs: list[CostLog] = Field(default_factory=list)
