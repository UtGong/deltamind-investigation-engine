import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    if not path.exists():
        raise FileNotFoundError(f"Missing predictions file: {path}")

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))

    return rows


def normalize_verdict(value: Any) -> str:
    if value is None:
        return "unknown"
    return str(value).strip().lower()


def normalize_stance(value: Any) -> str:
    if value is None:
        return "unknown"
    return str(value).strip().lower()


def domain_from_url(url: str | None) -> str | None:
    if not url:
        return None

    parsed = urlparse(url)
    domain = parsed.netloc or parsed.path.split("/", 1)[0]
    domain = domain.lower().removeprefix("www.")
    return domain or None


def source_key(evidence: dict[str, Any]) -> str:
    domain = domain_from_url(evidence.get("url"))
    if domain:
        return domain

    source_id = evidence.get("source_id")
    if source_id:
        return str(source_id)

    return "unknown_source"


def empty_stats() -> dict[str, Any]:
    return {
        "reward": 0.0,
        "penalty": 0.0,
        "neutral": 0.0,
        "supporting_stance_count": 0,
        "contradicting_stance_count": 0,
        "insufficient_stance_count": 0,
        "cases": set(),
        "evidence_ids": set(),
        "topics": set(),
        "examples": [],
    }


def update_stats(
    *,
    stats: dict[str, Any],
    case_id: str,
    evidence_id: str | None,
    claim: str,
    eval_topic: str,
    gold_verdict: str,
    predicted_verdict: str,
    stance: str,
    stance_confidence: float,
) -> None:
    if stance == "supports":
        stats["supporting_stance_count"] += 1
    elif stance == "contradicts":
        stats["contradicting_stance_count"] += 1
    elif stance == "insufficient":
        stats["insufficient_stance_count"] += 1

    reward = 0.0
    penalty = 0.0
    neutral = 0.0

    if gold_verdict == "supported":
        if stance == "supports":
            reward = stance_confidence
        elif stance == "contradicts":
            penalty = stance_confidence
        else:
            neutral = 1.0

    elif gold_verdict == "contradicted":
        if stance == "contradicts":
            reward = stance_confidence
        elif stance == "supports":
            penalty = stance_confidence
        else:
            neutral = 1.0

    elif gold_verdict == "unverifiable":
        if stance in {"supports", "contradicts"} and stance_confidence >= 0.7:
            penalty = 0.25 * stance_confidence
        else:
            neutral = 1.0

    else:
        neutral = 1.0

    stats["reward"] += reward
    stats["penalty"] += penalty
    stats["neutral"] += neutral
    stats["cases"].add(case_id)
    stats["topics"].add(eval_topic)

    if evidence_id:
        stats["evidence_ids"].add(evidence_id)

    if len(stats["examples"]) < 3:
        stats["examples"].append(
            {
                "case_id": case_id,
                "claim": claim,
                "eval_topic": eval_topic,
                "gold_verdict": gold_verdict,
                "predicted_verdict": predicted_verdict,
                "stance": stance,
                "stance_confidence": stance_confidence,
                "reward": round(reward, 4),
                "penalty": round(penalty, 4),
                "neutral": round(neutral, 4),
            }
        )


def learned_reliability(stats: dict[str, Any]) -> float:
    reward = float(stats["reward"])
    penalty = float(stats["penalty"])
    neutral = float(stats["neutral"])

    # Conservative Bayesian-style smoothing around 0.5.
    positive = reward + 1.0
    negative = penalty + 1.0
    neutral_mass = neutral * 0.15

    score = (positive + 0.5 * neutral_mass) / (
        positive + negative + neutral_mass
    )
    return round(max(0.05, min(0.98, score)), 4)


def reliability_uncertainty(stats: dict[str, Any]) -> float:
    observations = max(1, len(stats["evidence_ids"]))
    # Higher sample count means lower uncertainty, bounded for v1.
    return round(max(0.05, min(0.95, 1.0 / (observations ** 0.5))), 4)


def reliability_id(domain: str, claim_type: str, topic: str | None) -> str:
    raw = f"{domain}|{claim_type}|{topic or ''}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:32]
    return f"source_rel_{digest}"


def infer_eval_topic(rows: list[dict[str, Any]]) -> str:
    domains = {
        str(row.get("domain")).strip().lower()
        for row in rows
        if row.get("domain")
    }
    domains.discard("none")
    domains.discard("")

    if len(domains) == 1:
        return f"eval:{next(iter(domains))}"

    if len(domains) > 1:
        return "eval:mixed"

    return "eval:local"


def serialize_stats(source_stats: dict[str, dict[str, Any]]) -> dict[str, Any]:
    serializable = {}

    for source, stats in source_stats.items():
        serializable[source] = {
            "learned_reliability": learned_reliability(stats),
            "reliability_uncertainty": reliability_uncertainty(stats),
            "reward": round(stats["reward"], 4),
            "penalty": round(stats["penalty"], 4),
            "neutral": round(stats["neutral"], 4),
            "supporting_stance_count": stats["supporting_stance_count"],
            "contradicting_stance_count": stats["contradicting_stance_count"],
            "insufficient_stance_count": stats["insufficient_stance_count"],
            "case_count": len(stats["cases"]),
            "evidence_count": len(stats["evidence_ids"]),
            "topics": sorted(stats["topics"]),
            "examples": stats["examples"],
        }

    return serializable


def make_markdown_report(
    *,
    predictions_path: Path,
    source_stats: dict[str, dict[str, Any]],
    wrote_db: bool,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "# PIVOT Source Reliability Learning Report",
        "",
        f"Generated: `{now}`",
        "",
        f"Input predictions: `{predictions_path}`",
        f"Database write: `{'enabled' if wrote_db else 'disabled'}`",
        "",
        "## Summary",
        "",
        "| Source | Learned reliability | Uncertainty | Reward | Penalty | Neutral | Cases | Evidence |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]

    ranked = sorted(
        source_stats.items(),
        key=lambda item: (
            learned_reliability(item[1]),
            item[1]["reward"],
            -item[1]["penalty"],
        ),
        reverse=True,
    )

    for source, stats in ranked:
        lines.append(
            "| "
            + " | ".join(
                [
                    source,
                    str(learned_reliability(stats)),
                    str(reliability_uncertainty(stats)),
                    str(round(stats["reward"], 4)),
                    str(round(stats["penalty"], 4)),
                    str(round(stats["neutral"], 4)),
                    str(len(stats["cases"])),
                    str(len(stats["evidence_ids"])),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Examples", ""])

    for source, stats in ranked:
        lines.append(f"### {source}")
        lines.append("")

        if not stats["examples"]:
            lines.append("No examples.")
            lines.append("")
            continue

        lines.append("| Topic | Gold | Predicted | Stance | Reward | Penalty | Claim |")
        lines.append("|---|---|---|---|---:|---:|---|")

        for example in stats["examples"]:
            claim = str(example["claim"]).replace("|", "\\|")
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(example["eval_topic"]),
                        str(example["gold_verdict"]),
                        str(example["predicted_verdict"]),
                        str(example["stance"]),
                        str(example["reward"]),
                        str(example["penalty"]),
                        claim,
                    ]
                )
                + " |"
            )

        lines.append("")

    lines.extend(
        [
            "## Notes",
            "",
            "- This is Self-Learning v1.",
            "- Report mode is always enabled.",
            "- Database writes occur only when `--write-db` is passed.",
            "- `source_reliability` stores learned reliability by domain, claim type, and topic.",
            "- `sources.reliability_prior` is updated for matching source domains.",
            "",
        ]
    )

    return "\n".join(lines)


def build_source_stats(rows: list[dict[str, Any]], eval_topic: str) -> dict[str, dict[str, Any]]:
    source_stats: dict[str, dict[str, Any]] = defaultdict(empty_stats)

    for row in rows:
        if row.get("predicted_verdict") == "error":
            continue

        evidence_by_id = {
            evidence.get("evidence_id"): evidence
            for evidence in row.get("evidence", [])
            if evidence.get("evidence_id")
        }

        for stance in row.get("stances", []):
            evidence_id = stance.get("evidence_id")
            evidence = evidence_by_id.get(evidence_id)

            if evidence is None:
                continue

            source = source_key(evidence)

            update_stats(
                stats=source_stats[source],
                case_id=row.get("case_id", ""),
                evidence_id=evidence_id,
                claim=row.get("claim", ""),
                eval_topic=eval_topic,
                gold_verdict=normalize_verdict(row.get("gold_verdict")),
                predicted_verdict=normalize_verdict(row.get("predicted_verdict")),
                stance=normalize_stance(stance.get("stance")),
                stance_confidence=float(stance.get("confidence") or 0.0),
            )

    return source_stats


def write_to_db(
    *,
    serializable: dict[str, Any],
    topic: str,
    claim_type: str,
    json_report_path: Path,
) -> None:
    from app.db.models import SourceRecord, SourceReliabilityRecord
    from app.db.session import SessionLocal

    now = datetime.now(timezone.utc)

    with SessionLocal() as session:
        for domain, values in serializable.items():
            record_id = reliability_id(domain, claim_type, topic)

            record = session.get(SourceReliabilityRecord, record_id)

            metadata = {
                "source": "eval_learning_v1",
                "topic": topic,
                "claim_type": claim_type,
                "json_report": str(json_report_path),
                "reward": values["reward"],
                "penalty": values["penalty"],
                "neutral": values["neutral"],
                "supporting_stance_count": values["supporting_stance_count"],
                "contradicting_stance_count": values["contradicting_stance_count"],
                "insufficient_stance_count": values["insufficient_stance_count"],
                "examples": values["examples"],
            }

            if record is None:
                record = SourceReliabilityRecord(
                    reliability_id=record_id,
                    domain=domain,
                    claim_type=claim_type,
                    topic=topic,
                    reliability_mean=values["learned_reliability"],
                    reliability_uncertainty=values["reliability_uncertainty"],
                    num_observations=values["evidence_count"],
                    last_observed_at=now,
                    metadata_json=metadata,
                )
                session.add(record)
            else:
                record.reliability_mean = values["learned_reliability"]
                record.reliability_uncertainty = values["reliability_uncertainty"]
                record.num_observations = values["evidence_count"]
                record.last_observed_at = now
                record.metadata_json = metadata

            matching_sources = (
                session.query(SourceRecord)
                .filter(SourceRecord.domain.in_([domain, f"www.{domain}"]))
                .all()
            )

            for source in matching_sources:
                source.reliability_prior = values["learned_reliability"]
                source_metadata = dict(source.metadata_json or {})
                source_metadata["learned_reliability"] = {
                    "source": "eval_learning_v1",
                    "topic": topic,
                    "claim_type": claim_type,
                    "reliability_mean": values["learned_reliability"],
                    "reliability_uncertainty": values["reliability_uncertainty"],
                    "num_observations": values["evidence_count"],
                    "updated_at": now.isoformat(),
                }
                source.metadata_json = source_metadata

        session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update source reliability estimates from PIVOT eval outputs."
    )
    parser.add_argument(
        "--predictions",
        default="data/eval/predictions.jsonl",
        help="Prediction JSONL generated by run_pivot_eval_api.py.",
    )
    parser.add_argument(
        "--output",
        default="data/eval/reports/latest_learning_report.md",
        help="Markdown learning report output path.",
    )
    parser.add_argument(
        "--json-output",
        default="data/eval/reports/latest_learning_report.json",
        help="JSON learning report output path.",
    )
    parser.add_argument(
        "--topic",
        default=None,
        help="Learning topic. Defaults to inferred eval domain, e.g. eval:nba.",
    )
    parser.add_argument(
        "--claim-type",
        default="unknown",
        help="Claim type bucket for source_reliability records.",
    )
    parser.add_argument(
        "--write-db",
        action="store_true",
        help="Persist learned reliability into Postgres.",
    )

    args = parser.parse_args()

    predictions_path = Path(args.predictions)
    output_path = Path(args.output)
    json_output_path = Path(args.json_output)

    rows = load_jsonl(predictions_path)
    topic = args.topic or infer_eval_topic(rows)
    source_stats = build_source_stats(rows, topic)
    serializable = serialize_stats(source_stats)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        make_markdown_report(
            predictions_path=predictions_path,
            source_stats=source_stats,
            wrote_db=args.write_db,
        ),
        encoding="utf-8",
    )

    json_output_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "predictions": str(predictions_path),
                "topic": topic,
                "claim_type": args.claim_type,
                "write_db": args.write_db,
                "sources": serializable,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    if args.write_db and serializable:
        write_to_db(
            serializable=serializable,
            topic=topic,
            claim_type=args.claim_type,
            json_report_path=json_output_path,
        )

    print(f"Wrote learning report: {output_path}")
    print(f"Wrote learning JSON: {json_output_path}")
    print(f"Topic: {topic}")
    print(f"Claim type: {args.claim_type}")
    print(f"Database write: {'enabled' if args.write_db else 'disabled'}")

    if not serializable:
        print("No source updates generated. Check whether predictions include evidence and stances.")
        return

    print("")
    print("Learned source reliability:")
    for source, values in sorted(
        serializable.items(),
        key=lambda item: item[1]["learned_reliability"],
        reverse=True,
    ):
        print(
            f"- {source}: reliability={values['learned_reliability']} "
            f"uncertainty={values['reliability_uncertainty']} "
            f"reward={values['reward']} penalty={values['penalty']} "
            f"neutral={values['neutral']}"
        )


if __name__ == "__main__":
    main()
