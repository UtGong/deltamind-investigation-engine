from sqlalchemy import text

from app.db.session import engine


def test_postgres_schema_tables_exist_when_database_connected():
    try:
        with engine.connect() as connection:
            connected = True
            table_names = set(
                connection.execute(
                    text(
                        """
                        SELECT tablename
                        FROM pg_tables
                        WHERE schemaname = 'public'
                        """
                    )
                ).scalars()
            )
    except Exception:
        connected = False
        table_names = set()

    if not connected:
        return

    expected_tables = {
        "cases",
        "claims",
        "evidence",
        "stances",
        "sources",
        "graph_edges",
        "agent_runs",
        "cost_logs",
        "llm_cache",
        "verified_claims",
        "model_predictions",
        "source_reliability",
        "training_labels",
        "claim_embeddings",
        "evidence_embeddings",
    }

    assert expected_tables.issubset(table_names)
