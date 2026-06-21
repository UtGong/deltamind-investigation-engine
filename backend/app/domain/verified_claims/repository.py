import json
import sqlite3
from pathlib import Path

from app.core.config import get_settings
from app.core.constants import ClaimType, VerdictLabel
from app.domain.cases.models import utc_now
from app.domain.verified_claims.freshness import (
    compute_expires_at,
    get_cache_ttl_days,
    get_freshness_policy,
    is_expired,
)
from app.domain.verified_claims.models import VerifiedClaimRecord, normalize_claim_text
from app.schemas.agent import AtomicClaim, EvidenceItem, PivotVerdict, StanceResult


REUSABLE_VERDICTS = {
    VerdictLabel.SUPPORTED,
    VerdictLabel.CONTRADICTED,
    VerdictLabel.CONTESTED,
}


class VerifiedClaimRepository:
    def get_by_claim_text(self, claim_text: str) -> VerifiedClaimRecord | None:
        raise NotImplementedError

    def save_from_verdict(
        self,
        claim: AtomicClaim,
        verdict: PivotVerdict,
        evidence_count: int,
        evidence_items: list[EvidenceItem] | None = None,
        stance_results: list[StanceResult] | None = None,
    ) -> VerifiedClaimRecord | None:
        raise NotImplementedError

    def list(self) -> list[VerifiedClaimRecord]:
        raise NotImplementedError

    def clear(self) -> None:
        raise NotImplementedError


class InMemoryVerifiedClaimRepository(VerifiedClaimRepository):
    def __init__(self) -> None:
        self._records: dict[str, VerifiedClaimRecord] = {}

    def get_by_claim_text(self, claim_text: str) -> VerifiedClaimRecord | None:
        normalized = normalize_claim_text(claim_text)
        record = self._records.get(normalized)

        if record is None:
            return None

        if is_expired(record.expires_at):
            return None

        return record

    def save_from_verdict(
        self,
        claim: AtomicClaim,
        verdict: PivotVerdict,
        evidence_count: int,
        evidence_items: list[EvidenceItem] | None = None,
        stance_results: list[StanceResult] | None = None,
    ) -> VerifiedClaimRecord | None:
        if verdict.verdict not in REUSABLE_VERDICTS:
            return None

        normalized = normalize_claim_text(claim.claim_text)
        now = utc_now()
        existing = self._records.get(normalized)
        freshness_policy = get_freshness_policy(claim.claim_type)
        expires_at = compute_expires_at(claim.claim_type, now)

        evidence_snapshot = evidence_items or []
        stance_snapshot = stance_results or []

        record = VerifiedClaimRecord(
            normalized_claim_text=normalized,
            claim_text=claim.claim_text,
            claim_type=claim.claim_type,
            verdict=verdict.verdict,
            confidence=verdict.confidence,
            support_score=verdict.support_score,
            contradiction_score=verdict.contradiction_score,
            uncertainty_score=verdict.uncertainty_score,
            reason=verdict.reason,
            evidence_count=evidence_count,
            freshness_policy=freshness_policy,
            expires_at=expires_at,
            evidence_snapshot=evidence_snapshot,
            stance_snapshot=stance_snapshot,
            created_at=existing.created_at if existing else now,
            updated_at=now,
            metadata={
                "source": "pivot_verdict",
                "reusable": True,
                "storage": "memory",
                "ttl_days": get_cache_ttl_days(claim.claim_type),
                "evidence_snapshot_count": len(evidence_snapshot),
                "stance_snapshot_count": len(stance_snapshot),
            },
        )

        self._records[normalized] = record
        return record

    def list(self) -> list[VerifiedClaimRecord]:
        return list(self._records.values())

    def clear(self) -> None:
        self._records.clear()


class SqliteVerifiedClaimRepository(VerifiedClaimRepository):
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
        self._migrate_tables()

    def _create_tables(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS verified_claims (
                normalized_claim_text TEXT PRIMARY KEY,
                claim_text TEXT NOT NULL,
                claim_type TEXT NOT NULL,
                verdict TEXT NOT NULL,
                confidence REAL NOT NULL,
                support_score REAL NOT NULL,
                contradiction_score REAL NOT NULL,
                uncertainty_score REAL NOT NULL,
                reason TEXT NOT NULL,
                evidence_count INTEGER NOT NULL,
                freshness_policy TEXT NOT NULL DEFAULT 'legacy_no_expiry',
                expires_at TEXT,
                evidence_snapshot_json TEXT NOT NULL DEFAULT '[]',
                stance_snapshot_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        self.connection.commit()

    def _migrate_tables(self) -> None:
        columns = {
            row["name"]
            for row in self.connection.execute("PRAGMA table_info(verified_claims)").fetchall()
        }

        migrations = {
            "freshness_policy": (
                "ALTER TABLE verified_claims "
                "ADD COLUMN freshness_policy TEXT NOT NULL DEFAULT 'legacy_no_expiry'"
            ),
            "expires_at": (
                "ALTER TABLE verified_claims "
                "ADD COLUMN expires_at TEXT"
            ),
            "evidence_snapshot_json": (
                "ALTER TABLE verified_claims "
                "ADD COLUMN evidence_snapshot_json TEXT NOT NULL DEFAULT '[]'"
            ),
            "stance_snapshot_json": (
                "ALTER TABLE verified_claims "
                "ADD COLUMN stance_snapshot_json TEXT NOT NULL DEFAULT '[]'"
            ),
        }

        for column, statement in migrations.items():
            if column not in columns:
                self.connection.execute(statement)

        self.connection.commit()

    def get_by_claim_text(self, claim_text: str) -> VerifiedClaimRecord | None:
        normalized = normalize_claim_text(claim_text)

        row = self.connection.execute(
            """
            SELECT *
            FROM verified_claims
            WHERE normalized_claim_text = ?
            """,
            (normalized,),
        ).fetchone()

        if row is None:
            return None

        record = self._record_from_row(row)

        if is_expired(record.expires_at):
            return None

        return record

    def save_from_verdict(
        self,
        claim: AtomicClaim,
        verdict: PivotVerdict,
        evidence_count: int,
        evidence_items: list[EvidenceItem] | None = None,
        stance_results: list[StanceResult] | None = None,
    ) -> VerifiedClaimRecord | None:
        if verdict.verdict not in REUSABLE_VERDICTS:
            return None

        normalized = normalize_claim_text(claim.claim_text)
        existing = self.get_by_claim_text(claim.claim_text)
        now = utc_now()
        freshness_policy = get_freshness_policy(claim.claim_type)
        expires_at = compute_expires_at(claim.claim_type, now)

        evidence_snapshot = evidence_items or []
        stance_snapshot = stance_results or []

        record = VerifiedClaimRecord(
            normalized_claim_text=normalized,
            claim_text=claim.claim_text,
            claim_type=claim.claim_type,
            verdict=verdict.verdict,
            confidence=verdict.confidence,
            support_score=verdict.support_score,
            contradiction_score=verdict.contradiction_score,
            uncertainty_score=verdict.uncertainty_score,
            reason=verdict.reason,
            evidence_count=evidence_count,
            freshness_policy=freshness_policy,
            expires_at=expires_at,
            evidence_snapshot=evidence_snapshot,
            stance_snapshot=stance_snapshot,
            created_at=existing.created_at if existing else now,
            updated_at=now,
            metadata={
                "source": "pivot_verdict",
                "reusable": True,
                "storage": "sqlite",
                "ttl_days": get_cache_ttl_days(claim.claim_type),
                "evidence_snapshot_count": len(evidence_snapshot),
                "stance_snapshot_count": len(stance_snapshot),
            },
        )

        self.connection.execute(
            """
            INSERT INTO verified_claims (
                normalized_claim_text,
                claim_text,
                claim_type,
                verdict,
                confidence,
                support_score,
                contradiction_score,
                uncertainty_score,
                reason,
                evidence_count,
                freshness_policy,
                expires_at,
                evidence_snapshot_json,
                stance_snapshot_json,
                created_at,
                updated_at,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(normalized_claim_text)
            DO UPDATE SET
                claim_text = excluded.claim_text,
                claim_type = excluded.claim_type,
                verdict = excluded.verdict,
                confidence = excluded.confidence,
                support_score = excluded.support_score,
                contradiction_score = excluded.contradiction_score,
                uncertainty_score = excluded.uncertainty_score,
                reason = excluded.reason,
                evidence_count = excluded.evidence_count,
                freshness_policy = excluded.freshness_policy,
                expires_at = excluded.expires_at,
                evidence_snapshot_json = excluded.evidence_snapshot_json,
                stance_snapshot_json = excluded.stance_snapshot_json,
                updated_at = excluded.updated_at,
                metadata_json = excluded.metadata_json
            """,
            (
                record.normalized_claim_text,
                record.claim_text,
                record.claim_type.value,
                record.verdict.value,
                record.confidence,
                record.support_score,
                record.contradiction_score,
                record.uncertainty_score,
                record.reason,
                record.evidence_count,
                record.freshness_policy,
                record.expires_at.isoformat() if record.expires_at else None,
                json.dumps(
                    [item.model_dump(mode="json") for item in evidence_snapshot]
                ),
                json.dumps(
                    [item.model_dump(mode="json") for item in stance_snapshot]
                ),
                record.created_at.isoformat(),
                record.updated_at.isoformat(),
                json.dumps(record.metadata),
            ),
        )
        self.connection.commit()

        return record

    def list(self) -> list[VerifiedClaimRecord]:
        rows = self.connection.execute(
            """
            SELECT *
            FROM verified_claims
            ORDER BY updated_at DESC
            """
        ).fetchall()

        return [self._record_from_row(row) for row in rows]

    def clear(self) -> None:
        self.connection.execute("DELETE FROM verified_claims")
        self.connection.commit()

    def _record_from_row(self, row: sqlite3.Row) -> VerifiedClaimRecord:
        evidence_snapshot = [
            EvidenceItem.model_validate(item)
            for item in json.loads(row["evidence_snapshot_json"] or "[]")
        ]
        stance_snapshot = [
            StanceResult.model_validate(item)
            for item in json.loads(row["stance_snapshot_json"] or "[]")
        ]

        return VerifiedClaimRecord(
            normalized_claim_text=row["normalized_claim_text"],
            claim_text=row["claim_text"],
            claim_type=ClaimType(row["claim_type"]),
            verdict=VerdictLabel(row["verdict"]),
            confidence=row["confidence"],
            support_score=row["support_score"],
            contradiction_score=row["contradiction_score"],
            uncertainty_score=row["uncertainty_score"],
            reason=row["reason"],
            evidence_count=row["evidence_count"],
            freshness_policy=row["freshness_policy"],
            expires_at=row["expires_at"],
            evidence_snapshot=evidence_snapshot,
            stance_snapshot=stance_snapshot,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=json.loads(row["metadata_json"]),
        )


settings = get_settings()

if settings.database_backend.lower().strip() == "postgres":
    from app.domain.verified_claims.postgres_repository import (
        PostgresVerifiedClaimRepository,
    )

    verified_claim_repository = PostgresVerifiedClaimRepository()

settings = get_settings()

if settings.database_backend.lower().strip() == "postgres":
    from app.domain.verified_claims.postgres_repository import (
        PostgresVerifiedClaimRepository,
    )

    verified_claim_repository = PostgresVerifiedClaimRepository()
else:
    verified_claim_repository = SqliteVerifiedClaimRepository(
        settings.verified_claim_db_path
    )
