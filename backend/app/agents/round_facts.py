import re
from dataclasses import dataclass


ROUND_PATTERN = re.compile(r"\bround\s+of\s+(\d+)\b", flags=re.IGNORECASE)


@dataclass(frozen=True)
class RoundFact:
    value: int
    text: str


def infer_round_stance(claim_text: str, evidence_text: str) -> str | None:
    claim_fact = extract_round_fact(claim_text)
    evidence_fact = extract_round_fact(evidence_text)

    if claim_fact is None or evidence_fact is None:
        return None

    if claim_fact.value == evidence_fact.value:
        return "supports"

    return "contradicts"


def build_round_correction(
    claim_text: str,
    evidence_texts: list[str],
) -> tuple[str, str, str] | None:
    claim_fact = extract_round_fact(claim_text)
    if claim_fact is None:
        return None

    for evidence_text in evidence_texts:
        evidence_fact = extract_round_fact(evidence_text)
        if evidence_fact is None or evidence_fact.value == claim_fact.value:
            continue

        corrected_round = f"Round of {evidence_fact.value}"
        corrected_claim = ROUND_PATTERN.sub(corrected_round, claim_text, count=1)

        return corrected_claim, claim_fact.text, corrected_round

    return None


def extract_round_fact(text: str) -> RoundFact | None:
    match = ROUND_PATTERN.search(text)
    if match is None:
        return None

    value = int(match.group(1))
    return RoundFact(value=value, text=match.group(0))
