from app.core.constants import AgentRunStatus, CostType
from app.db.session import check_database_connection
from app.domain.audit.postgres_repository import PostgresAuditRepository
from app.domain.cases.models import utc_now
from app.schemas.audit import AgentRun, CostLog


def test_postgres_audit_repository_roundtrip_when_database_connected():
    health = check_database_connection()

    if not health["connected"]:
        return

    repository = PostgresAuditRepository()
    case_id = "case_audit_postgres_test"

    repository.clear_case(case_id)

    now = utc_now()

    agent_run = AgentRun(
        agent_run_id="run_audit_postgres_test",
        case_id=case_id,
        agent_name="test_agent",
        status=AgentRunStatus.COMPLETED,
        provider="test_provider",
        model="test_model",
        started_at=now,
        completed_at=now,
        input_summary='{"input": true}',
        output_summary='{"output": true}',
        input_hash="input_hash",
        output_hash="output_hash",
        metadata={"stage": "test_stage"},
    )

    cost_log = CostLog(
        cost_id="cost_audit_postgres_test",
        case_id=case_id,
        cost_type=list(CostType)[0],
        provider="test_provider",
        units=12,
        unit_name="tokens",
        estimated_cost_usd=0.001,
        metadata={"purpose": "test"},
    )

    repository.add_agent_run(agent_run)
    repository.add_cost_log(cost_log)

    trail = repository.get_trail(case_id)

    assert trail.case_id == case_id
    assert len(trail.agent_runs) == 1
    assert len(trail.cost_logs) == 1

    restored_run = trail.agent_runs[0]
    assert restored_run.agent_run_id == agent_run.agent_run_id
    assert restored_run.agent_name == "test_agent"
    assert restored_run.status == AgentRunStatus.COMPLETED
    assert restored_run.provider == "test_provider"
    assert restored_run.model == "test_model"
    assert restored_run.input_hash == "input_hash"
    assert restored_run.output_hash == "output_hash"
    assert restored_run.metadata["stage"] == "test_stage"

    restored_cost = trail.cost_logs[0]
    assert restored_cost.cost_id == cost_log.cost_id
    assert restored_cost.cost_type == list(CostType)[0]
    assert restored_cost.units == 12
    assert restored_cost.unit_name == "tokens"
    assert restored_cost.estimated_cost_usd == 0.001
    assert restored_cost.metadata["purpose"] == "test"

    repository.clear_case(case_id)
    assert repository.get_trail(case_id).agent_runs == []
    assert repository.get_trail(case_id).cost_logs == []
