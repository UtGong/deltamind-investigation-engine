import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def post_json(url: str, payload: dict[str, Any], timeout: int = 180) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8")
        try:
            detail = json.loads(body)
        except json.JSONDecodeError:
            detail = {"raw_error": body}

        return {
            "error": True,
            "status_code": error.code,
            "detail": detail,
        }
    except (urllib.error.URLError, ConnectionResetError, TimeoutError, OSError) as error:
        return {
            "error": True,
            "status_code": None,
            "detail": {
                "error_type": type(error).__name__,
                "error_message": str(error),
                "url": url,
            },
        }
    except (urllib.error.URLError, ConnectionResetError, TimeoutError, OSError) as error:
        return {
            "error": True,
            "status_code": None,
            "detail": {
                "error_type": type(error).__name__,
                "error_message": str(error),
                "url": url,
            },
        }


def normalize_verdict(value: str | None) -> str:
    return (value or "unknown").strip().lower()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))

    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run PIVOT evaluation cases through the local API."
    )
    parser.add_argument(
        "--input",
        default="data/eval/gold_claims.jsonl",
        help="Gold claim JSONL file.",
    )
    parser.add_argument(
        "--output",
        default="data/eval/predictions.jsonl",
        help="Prediction output JSONL file.",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000/api/v1",
        help="API base URL.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.0,
        help="Seconds to sleep between cases.",
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    gold_rows = load_jsonl(input_path)
    predictions: list[dict[str, Any]] = []

    correct = 0
    completed = 0

    for index, row in enumerate(gold_rows, start=1):
        claim = row["claim"]
        gold_verdict = normalize_verdict(row.get("gold_verdict"))

        print(f"[{index}/{len(gold_rows)}] {row.get('id')}: {claim}")

        case_response = post_json(
            f"{args.base_url}/cases",
            {
                "input_type": "claim",
                "input_text": claim,
                "title": f"Eval: {row.get('id', index)}",
            },
        )

        if case_response.get("error"):
            prediction = {
                **row,
                "case_create_error": case_response,
                "predicted_verdict": "error",
                "correct": False,
            }
            predictions.append(prediction)
            continue

        case_id = case_response["case_id"]

        result = post_json(f"{args.base_url}/cases/{case_id}/investigate", {})

        if result.get("error") or "detail" in result:
            prediction = {
                **row,
                "case_id": case_id,
                "investigation_error": result,
                "predicted_verdict": "error",
                "correct": False,
            }
            predictions.append(prediction)
            continue

        predicted_verdict = normalize_verdict(result.get("case_verdict"))
        is_correct = predicted_verdict == gold_verdict

        corrections = result.get("corrections", [])
        active_corrections = [
            correction
            for correction in corrections
            if correction.get("needs_correction")
        ]
        corrected_claims = [
            correction.get("corrected_claim")
            for correction in active_corrections
            if correction.get("corrected_claim")
        ]

        compact_evidence = [
            {
                "evidence_id": evidence.get("evidence_id"),
                "claim_id": evidence.get("claim_id"),
                "source_id": evidence.get("source_id"),
                "independence_group": evidence.get("independence_group"),
                "url": evidence.get("url"),
                "title": evidence.get("title"),
                "reliability": evidence.get("reliability"),
                "specificity": evidence.get("specificity"),
                "independence": evidence.get("independence"),
                "freshness": evidence.get("freshness"),
                "metadata": evidence.get("metadata", {}),
            }
            for evidence in result.get("evidence", [])
        ]

        compact_stances = [
            {
                "claim_id": stance.get("claim_id"),
                "evidence_id": stance.get("evidence_id"),
                "stance": stance.get("stance"),
                "confidence": stance.get("confidence"),
                "reason": stance.get("reason"),
            }
            for stance in result.get("stances", [])
        ]

        completed += 1
        correct += int(is_correct)

        prediction = {
            **row,
            "case_id": case_id,
            "predicted_verdict": predicted_verdict,
            "confidence": result.get("confidence"),
            "correct": is_correct,
            "evidence_count": len(result.get("evidence", [])),
            "stance_count": len(result.get("stances", [])),
            "claim_count": len(result.get("claims", [])),
            "correction_count": len(active_corrections),
            "needs_correction": bool(active_corrections),
            "corrected_claims": corrected_claims,
            "corrections": corrections,
            "evidence": compact_evidence,
            "stances": compact_stances,
            "verdicts": result.get("verdicts", []),
        }

        predictions.append(prediction)

        print(
            f"  predicted={predicted_verdict} "
            f"gold={gold_verdict} "
            f"correct={is_correct} "
            f"confidence={result.get('confidence')}"
        )

        if args.sleep > 0:
            time.sleep(args.sleep)

    write_jsonl(output_path, predictions)

    label_metrics: dict[str, dict[str, int | float]] = {}

    for prediction in predictions:
        gold = normalize_verdict(prediction.get("gold_verdict"))
        predicted = normalize_verdict(prediction.get("predicted_verdict"))

        if gold not in label_metrics:
            label_metrics[gold] = {
                "total": 0,
                "correct": 0,
                "accuracy": 0.0,
            }

        label_metrics[gold]["total"] += 1
        label_metrics[gold]["correct"] += int(predicted == gold)

    for metrics in label_metrics.values():
        total = int(metrics["total"])
        correct_count = int(metrics["correct"])
        metrics["accuracy"] = round(correct_count / total, 4) if total else 0.0

    confusion: dict[str, dict[str, int]] = {}

    for prediction in predictions:
        gold = normalize_verdict(prediction.get("gold_verdict"))
        predicted = normalize_verdict(prediction.get("predicted_verdict"))

        if gold not in confusion:
            confusion[gold] = {}

        confusion[gold][predicted] = confusion[gold].get(predicted, 0) + 1

    summary = {
        "input": str(input_path),
        "output": str(output_path),
        "total": len(gold_rows),
        "completed": completed,
        "correct": correct,
        "accuracy": round(correct / completed, 4) if completed else 0.0,
        "errors": len([row for row in predictions if row.get("predicted_verdict") == "error"]),
        "label_metrics": label_metrics,
        "confusion": confusion,
    }

    summary_path = output_path.with_suffix(".summary.json")
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )

    print("\nSUMMARY")
    print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
