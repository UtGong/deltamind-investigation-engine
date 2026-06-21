from app.schemas.audit import AgentRun, AuditTrail, CostLog


class AuditRepository:
    def add_agent_run(self, agent_run: AgentRun) -> AgentRun:
        raise NotImplementedError

    def add_cost_log(self, cost_log: CostLog) -> CostLog:
        raise NotImplementedError

    def get_trail(self, case_id: str) -> AuditTrail:
        raise NotImplementedError


class InMemoryAuditRepository(AuditRepository):
    def __init__(self) -> None:
        self._agent_runs: dict[str, list[AgentRun]] = {}
        self._cost_logs: dict[str, list[CostLog]] = {}

    def add_agent_run(self, agent_run: AgentRun) -> AgentRun:
        self._agent_runs.setdefault(agent_run.case_id, []).append(agent_run)
        return agent_run

    def add_cost_log(self, cost_log: CostLog) -> CostLog:
        self._cost_logs.setdefault(cost_log.case_id, []).append(cost_log)
        return cost_log

    def get_trail(self, case_id: str) -> AuditTrail:
        return AuditTrail(
            case_id=case_id,
            agent_runs=self._agent_runs.get(case_id, []),
            cost_logs=self._cost_logs.get(case_id, []),
        )


from app.core.config import get_settings

settings = get_settings()

if settings.database_backend.lower().strip() == "postgres":
    from app.domain.audit.postgres_repository import PostgresAuditRepository

    audit_repository = PostgresAuditRepository()
else:
    audit_repository = InMemoryAuditRepository()
