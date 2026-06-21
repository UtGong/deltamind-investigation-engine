import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))

    return rows


def escape_table_cell(value: object) -> str:
    text = str(value if value is not None else "")
    return text.replace("|", "\\|").replace("\n", " ").strip()


def verdict_icon(correct: bool) -> str:
    return "✅" if correct else "❌"


def make_markdown_report(
    *,
    summary: dict[str, Any],
    predictions: list[dict[str, Any]],
    title: str,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines: list[str] = []

    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"Generated: `{now}`")
    lines.append("")
    lines.append("## Overall Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    lines.append(f"| Total cases | {summary.get('total', 0)} |")
    lines.append(f"| Completed | {summary.get('completed', 0)} |")
    lines.append(f"| Correct | {summary.get('correct', 0)} |")
    lines.append(f"| Errors | {summary.get('errors', 0)} |")
    lines.append(f"| Accuracy | {summary.get('accuracy', 0.0)} |")
    lines.append("")

    label_metrics = summary.get("label_metrics", {})
    if label_metrics:
        lines.append("## Per-Label Accuracy")
        lines.append("")
        lines.append("| Gold label | Correct | Total | Accuracy |")
        lines.append("|---|---:|---:|---:|")

        for label in sorted(label_metrics):
            metrics = label_metrics[label]
            lines.append(
                "| "
                + " | ".join(
                    [
                        escape_table_cell(label),
                        escape_table_cell(metrics.get("correct", 0)),
                        escape_table_cell(metrics.get("total", 0)),
                        escape_table_cell(metrics.get("accuracy", 0.0)),
                    ]
                )
                + " |"
            )

        lines.append("")

    confusion = summary.get("confusion", {})
    if confusion:
        predicted_labels = sorted(
            {
                predicted
                for predicted_counts in confusion.values()
                for predicted in predicted_counts.keys()
            }
        )

        lines.append("## Confusion Matrix")
        lines.append("")
        lines.append("| Gold \\ Predicted | " + " | ".join(predicted_labels) + " |")
        lines.append("|---" + "|---:" * len(predicted_labels) + "|")

        for gold in sorted(confusion):
            row = [gold]
            for predicted in predicted_labels:
                row.append(str(confusion.get(gold, {}).get(predicted, 0)))

            lines.append("| " + " | ".join(escape_table_cell(cell) for cell in row) + " |")

        lines.append("")

    failed = [row for row in predictions if not row.get("correct")]

    lines.append("## Failed Cases")
    lines.append("")

    if not failed:
        lines.append("No failed cases.")
    else:
        lines.append("| ID | Gold | Predicted | Confidence | Claim |")
        lines.append("|---|---|---|---:|---|")

        for row in failed:
            lines.append(
                "| "
                + " | ".join(
                    [
                        escape_table_cell(row.get("id")),
                        escape_table_cell(row.get("gold_verdict")),
                        escape_table_cell(row.get("predicted_verdict")),
                        escape_table_cell(row.get("confidence")),
                        escape_table_cell(row.get("claim")),
                    ]
                )
                + " |"
            )

    lines.append("")

    lines.append("## All Cases")
    lines.append("")
    lines.append("| Result | ID | Gold | Predicted | Confidence | Evidence | Stances | Claim |")
    lines.append("|---|---|---|---|---:|---:|---:|---|")

    for row in predictions:
        lines.append(
            "| "
            + " | ".join(
                [
                    verdict_icon(bool(row.get("correct"))),
                    escape_table_cell(row.get("id")),
                    escape_table_cell(row.get("gold_verdict")),
                    escape_table_cell(row.get("predicted_verdict")),
                    escape_table_cell(row.get("confidence")),
                    escape_table_cell(row.get("evidence_count")),
                    escape_table_cell(row.get("stance_count")),
                    escape_table_cell(row.get("claim")),
                ]
            )
            + " |"
        )

    lines.append("")
    lines.append("## Source Files")
    lines.append("")
    lines.append(f"- Summary: `{summary.get('output', '')}.summary.json`")
    lines.append(f"- Predictions: `{summary.get('output', '')}`")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a Markdown report from PIVOT eval predictions."
    )
    parser.add_argument(
        "--predictions",
        default="data/eval/predictions.jsonl",
        help="Prediction JSONL file.",
    )
    parser.add_argument(
        "--summary",
        default="data/eval/predictions.summary.json",
        help="Summary JSON file.",
    )
    parser.add_argument(
        "--output",
        default="data/eval/reports/latest_eval_report.md",
        help="Markdown report output path.",
    )
    parser.add_argument(
        "--title",
        default="PIVOT Evaluation Report",
        help="Markdown report title.",
    )

    args = parser.parse_args()

    predictions_path = Path(args.predictions)
    summary_path = Path(args.summary)
    output_path = Path(args.output)

    predictions = load_jsonl(predictions_path)
    summary = load_json(summary_path)

    report = make_markdown_report(
        summary=summary,
        predictions=predictions,
        title=args.title,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")

    print(f"Wrote report: {output_path}")


if __name__ == "__main__":
    main()
