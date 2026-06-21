from app.domain.llm_cache.postgres_repository import PostgresLLMCacheRepository
from app.db.session import check_database_connection


def test_postgres_llm_cache_repository_roundtrip_when_database_connected():
    health = check_database_connection()

    if not health["connected"]:
        return

    repository = PostgresLLMCacheRepository()
    repository.clear()

    repository.save(
        request_hash="test_hash",
        cache_namespace="test_namespace",
        provider_name="test_provider",
        model="test_model",
        content='{"ok": true}',
        input_tokens=11,
        output_tokens=7,
        estimated_cost_usd=0.02,
        metadata={"test": True},
    )

    cached = repository.get("test_hash")

    assert cached is not None
    assert cached.request_hash == "test_hash"
    assert cached.cache_namespace == "test_namespace"
    assert cached.provider_name == "test_provider"
    assert cached.model == "test_model"
    assert cached.content == '{"ok": true}'
    assert cached.input_tokens == 11
    assert cached.output_tokens == 7
    assert cached.estimated_cost_usd == 0.02
    assert cached.metadata["test"] is True
    assert cached.hit_count == 0

    repository.record_hit("test_hash")

    cached_after_hit = repository.get("test_hash")
    assert cached_after_hit is not None
    assert cached_after_hit.hit_count == 1

    stats = repository.stats()
    assert stats["backend"] == "postgres"
    assert stats["entry_count"] == 1
    assert stats["total_hits"] == 1

    repository.clear()
