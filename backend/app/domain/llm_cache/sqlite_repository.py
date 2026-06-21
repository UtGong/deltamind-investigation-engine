import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.domain.llm_cache.base import CachedLLMEntry


class SQLiteLLMCacheRepository:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self.connection = sqlite3.connect(
            db_path,
            check_same_thread=False,
        )
        self.connection.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_cache (
                request_hash TEXT PRIMARY KEY,
                cache_namespace TEXT NOT NULL,
                provider_name TEXT NOT NULL,
                model TEXT,
                content TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                estimated_cost_usd REAL NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                last_used_at TEXT NOT NULL,
                hit_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self.connection.commit()

    def get(self, request_hash: str) -> CachedLLMEntry | None:
        row = self.connection.execute(
            """
            SELECT *
            FROM llm_cache
            WHERE request_hash = ?
            """,
            (request_hash,),
        ).fetchone()

        if row is None:
            return None

        return CachedLLMEntry(
            request_hash=row["request_hash"],
            cache_namespace=row["cache_namespace"],
            provider_name=row["provider_name"],
            model=row["model"],
            content=row["content"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            estimated_cost_usd=row["estimated_cost_usd"],
            metadata=json.loads(row["metadata_json"] or "{}"),
            hit_count=row["hit_count"],
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
        now = self._now()

        self.connection.execute(
            """
            INSERT INTO llm_cache (
                request_hash,
                cache_namespace,
                provider_name,
                model,
                content,
                input_tokens,
                output_tokens,
                estimated_cost_usd,
                metadata_json,
                created_at,
                updated_at,
                last_used_at,
                hit_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(request_hash)
            DO UPDATE SET
                cache_namespace = excluded.cache_namespace,
                provider_name = excluded.provider_name,
                model = excluded.model,
                content = excluded.content,
                input_tokens = excluded.input_tokens,
                output_tokens = excluded.output_tokens,
                estimated_cost_usd = excluded.estimated_cost_usd,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at,
                last_used_at = excluded.last_used_at
            """,
            (
                request_hash,
                cache_namespace,
                provider_name,
                model,
                content,
                input_tokens,
                output_tokens,
                estimated_cost_usd,
                json.dumps(metadata),
                now,
                now,
                now,
            ),
        )
        self.connection.commit()

    def record_hit(self, request_hash: str) -> None:
        now = self._now()

        self.connection.execute(
            """
            UPDATE llm_cache
            SET
                hit_count = hit_count + 1,
                updated_at = ?,
                last_used_at = ?
            WHERE request_hash = ?
            """,
            (
                now,
                now,
                request_hash,
            ),
        )
        self.connection.commit()

    def clear(self) -> None:
        self.connection.execute("DELETE FROM llm_cache")
        self.connection.commit()

    def stats(self) -> dict:
        row = self.connection.execute(
            """
            SELECT
                COUNT(*) AS entry_count,
                COALESCE(SUM(hit_count), 0) AS total_hits,
                COALESCE(SUM(input_tokens), 0) AS cached_input_tokens,
                COALESCE(SUM(output_tokens), 0) AS cached_output_tokens,
                COALESCE(SUM(estimated_cost_usd), 0.0) AS cached_estimated_cost_usd
            FROM llm_cache
            """
        ).fetchone()

        return {
            "backend": "sqlite",
            "db_path": self.db_path,
            "entry_count": row["entry_count"],
            "total_hits": row["total_hits"],
            "cached_input_tokens": row["cached_input_tokens"],
            "cached_output_tokens": row["cached_output_tokens"],
            "cached_estimated_cost_usd": row["cached_estimated_cost_usd"],
        }

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
