import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.domain.investigations.service import investigation_service


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export a trust certificate from a completed investigation case."
    )
    parser.add_argument(
        "--case-id",
        required=True,
        help="Case ID whose completed investigation contains a trust certificate.",
    )
    parser.add_argument(
        "--output",
        default="data/certificates/trust_certificate.json",
        help="Output JSON path.",
    )
    args = parser.parse_args()

    result = investigation_service.get_result(args.case_id)

    if result.trust_certificate is None:
        raise SystemExit(
            f"No trust certificate is available for case_id={args.case_id}. "
            "Run the investigation first."
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        result.trust_certificate.model_dump_json(indent=2),
        encoding="utf-8",
    )

    print(f"Wrote trust certificate: {output_path}")
    print(f"certificate_id: {result.trust_certificate.certificate_id}")
    print(f"case_id: {result.trust_certificate.case_id}")
    print(f"lifecycle_status: {result.trust_certificate.lifecycle_status}")
    print(f"overall_verdict: {result.trust_certificate.overall_verdict}")
    print(f"trust_index: {result.trust_certificate.trust_index}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
