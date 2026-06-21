from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import LLMCacheRecord
from app.db.session import SessionLocal
from app.domain.llm_cache.base import CachedLLMEntry


class PostgresLLMCacheRepository:
    def get(self, request_hash: str) -> CachedLLMEntry | None:
        with SessionLocal() as session:
            record = session.get(LLMCacheRecord, request_hash)

            if record is None:
                return None

            return CachedLLMEntry(
                request_hash=record.request_hash,
                cache_namespace=record.cache_namespace,
                provider_name=record.provider_name,
                model=record.model,
                content=record.content,
                input_tokens=record.input_tokens,
                output_tokens=record.output_tokens,
                estimated_cost_usd=record.estimated_cost_usd,
                metadata=record.metadata_json or {},
                hit_count=record.hit_count,
            )

    def save(
        self,
        request_hash: str,
        cache_namespace: str,
        provider_name: str,
        model: str | None,
        content: str,
        input_tokens: int,
        output_tokens: int,
        estimated_cost_usd: float,
        metadata: dict,
    ) -> None:
        now = datetime.now(timezone.utc)

        values = {
            "request_hash": request_hash,
            "cache_namespace": cache_namespace,
            "provider_name": provider_name,
            "model": model,
            "content": content,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": estimated_cost_usd,
            "metadata_json": metadata,
            "last_used_at": now,
            "hit_count": 0,
        }

        statement = insert(LLMCacheRecord).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[LLMCacheRecord.request_hash],
            set_={
                "cache_namespace": cache_namespace,
                "provider_name": provider_name,
                "model": model,
                "content": content,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "estimated_cost_usd": estimated_cost_usd,
                "metadata_json": metadata,
                "last_used_at": now,
                "updated_at": now,
            },
        )

        with SessionLocal() as session:
            session.execute(statement)
            session.commit()

    def record_hit(self, request_hash: str) -> None:
        now = datetime.now(timezone.utc)

        with SessionLocal() as session:
            record = session.get(LLMCacheRecord, request_hash)

            if record is None:
                return

            record.hit_count += 1
            record.last_used_at = now
            record.updated_at = now
            session.commit()

    def clear(self) -> None:
        with SessionLocal() as session:
            session.query(LLMCacheRecord).delete()
            session.commit()

    def stats(self) -> dict:
        with SessionLocal() as session:
            row = session.execute(
                select(
                    func.count(LLMCacheRecord.request_hash),
                    func.coalesce(func.sum(LLMCacheRecord.hit_count), 0),
                    func.coalesce(func.sum(LLMCacheRecord.input_tokens), 0),
                    func.coalesce(func.sum(LLMCacheRecord.output_tokens), 0),
                    func.coalesce(func.sum(LLMCacheRecord.estimated_cost_usd), 0.0),
                )
            ).one()

        return {
            "backend": "postgres",
            "db_path": None,
            "entry_count": row[0],
            "total_hits": row[1],
            "cached_input_tokens": row[2],
            "cached_output_tokens": row[3],
            "cached_estimated_cost_usd": row[4],
        }
