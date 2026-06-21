import argparse
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.db.models import (
    CaseRecord as DBCaseRecord,
    ClaimRecord,
    EvidenceRecord,
    SourceRecord,
    StanceRecord,
)
from app.db.session import SessionLocal


def to_jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, bytes):
        return value.hex()

    if isinstance(value, list):
        return [to_jsonable(item) for item in value]

    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}

    return value


def row_to_dict(row: Any) -> dict[str, Any]:
    output: dict[str, Any] = {}

    for column in row.__table__.columns:
        output[column.name] = to_jsonable(getattr(row, column.name))

    return output


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def query_rows(session, model, case_id: str | None = None) -> list[Any]:
    query = session.query(model)

    if case_id and hasattr(model, "case_id"):
        query = query.filter(model.case_id == case_id)

    return query.all()


def export_sources(session, out_dir: Path, case_id: str | None = None) -> int:
    if case_id:
        source_ids = {
            row.source_id
            for row in session.query(EvidenceRecord)
            .filter(EvidenceRecord.case_id == case_id)
            .all()
        }

        rows = (
            session.query(SourceRecord)
            .filter(SourceRecord.source_id.in_(source_ids))
            .all()
            if source_ids
            else []
        )
    else:
        rows = session.query(SourceRecord).all()

    write_jsonl(out_dir / "sources.jsonl", [row_to_dict(row) for row in rows])
    return len(rows)


def export_table(
    session,
    model,
    out_dir: Path,
    filename: str,
    case_id: str | None = None,
) -> int:
    rows = query_rows(session, model, case_id=case_id)
    write_jsonl(out_dir / filename, [row_to_dict(row) for row in rows])
    return len(rows)


def export_claim_examples(session, out_dir: Path, case_id: str | None = None) -> int:
    claim_query = session.query(ClaimRecord)

    if case_id:
        claim_query = claim_query.filter(ClaimRecord.case_id == case_id)

    claims = claim_query.all()
    examples: list[dict[str, Any]] = []

    for claim in claims:
        case = session.get(DBCaseRecord, claim.case_id)

        evidence_rows = (
            session.query(EvidenceRecord)
            .filter(
                EvidenceRecord.case_id == claim.case_id,
                EvidenceRecord.claim_id == claim.claim_id,
            )
            .all()
        )

        stance_rows = (
            session.query(StanceRecord)
            .filter(
                StanceRecord.case_id == claim.case_id,
                StanceRecord.claim_id == claim.claim_id,
            )
            .all()
        )

        source_ids = {row.source_id for row in evidence_rows}
        source_rows = (
            session.query(SourceRecord)
            .filter(SourceRecord.source_id.in_(source_ids))
            .all()
            if source_ids
            else []
        )

        examples.append(
            {
                "case": row_to_dict(case) if case else None,
                "claim": row_to_dict(claim),
                "evidence": [row_to_dict(row) for row in evidence_rows],
                "stances": [row_to_dict(row) for row in stance_rows],
                "sources": [row_to_dict(row) for row in source_rows],
                "label": {
                    "verdict": claim.final_verdict,
                    "correctness_score": claim.correctness_score,
                    "trust_score": claim.trust_score,
                    "uncertainty_score": claim.uncertainty_score,
                },
            }
        )

    write_jsonl(out_dir / "claim_verification_examples.jsonl", examples)
    return len(examples)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export normalized PIVOT verification data from Postgres to JSONL."
    )
    parser.add_argument(
        "--out",
        default="data/exports/pivot_dataset",
        help="Output directory for JSONL files.",
    )
    parser.add_argument(
        "--case-id",
        default=None,
        help="Optional case_id filter for exporting one investigation.",
    )

    args = parser.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as session:
        summary = {
            "case_id_filter": args.case_id,
            "output_dir": str(out_dir),
            "counts": {
                "cases": export_table(
                    session,
                    DBCaseRecord,
                    out_dir,
                    "cases.jsonl",
                    case_id=args.case_id,
                ),
                "claims": export_table(
                    session,
                    ClaimRecord,
                    out_dir,
                    "claims.jsonl",
                    case_id=args.case_id,
                ),
                "evidence": export_table(
                    session,
                    EvidenceRecord,
                    out_dir,
                    "evidence.jsonl",
                    case_id=args.case_id,
                ),
                "stances": export_table(
                    session,
                    StanceRecord,
                    out_dir,
                    "stances.jsonl",
                    case_id=args.case_id,
                ),
                "sources": export_sources(
                    session,
                    out_dir,
                    case_id=args.case_id,
                ),
                "claim_verification_examples": export_claim_examples(
                    session,
                    out_dir,
                    case_id=args.case_id,
                ),
            },
        }

    (out_dir / "export_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
