import re
from dataclasses import dataclass


TEAM_ALIASES = {
    "u s": "usa",
    "u s a": "usa",
    "us": "usa",
    "usa": "usa",
    "united states": "usa",
    "united states men's national team": "usa",
    "usmnt": "usa",
}
TEAM_PATTERN = r"(?:USA|US|U\.S\.|United States|[A-Z][A-Za-z']*(?:\s+[A-Z][A-Za-z']*){0,4})"


@dataclass(frozen=True)
class ScoreFact:
    winner: str | None
    loser: str | None
    winner_goals: int
    loser_goals: int
    score_text: str


def infer_score_stance(claim_text: str, evidence_text: str) -> str | None:
    claim_fact = extract_score_fact(claim_text)
    evidence_fact = extract_score_fact(evidence_text)

    if claim_fact is None or evidence_fact is None:
        return None

    if not _same_matchup(claim_fact, evidence_fact):
        return None

    if (
        claim_fact.winner == evidence_fact.winner
        and claim_fact.loser == evidence_fact.loser
        and claim_fact.winner_goals == evidence_fact.winner_goals
        and claim_fact.loser_goals == evidence_fact.loser_goals
    ):
        return "supports"

    if claim_fact.winner == evidence_fact.winner and claim_fact.loser == evidence_fact.loser:
        return "contradicts"

    return None


def build_score_correction(claim_text: str, evidence_texts: list[str]) -> tuple[str, str, str] | None:
    claim_fact = extract_score_fact(claim_text)
    if claim_fact is None:
        return None

    for evidence_text in evidence_texts:
        evidence_fact = extract_score_fact(evidence_text)
        if evidence_fact is None or not _same_matchup(claim_fact, evidence_fact):
            continue

        if (
            claim_fact.winner_goals == evidence_fact.winner_goals
            and claim_fact.loser_goals == evidence_fact.loser_goals
            and claim_fact.winner == evidence_fact.winner
            and claim_fact.loser == evidence_fact.loser
        ):
            continue

        winner = _display_team(evidence_fact.winner or claim_fact.winner)
        loser = _display_team(evidence_fact.loser or claim_fact.loser)
        if winner is None or loser is None:
            continue

        corrected_claim = re.sub(
            r"\b\d+\s*[-–]\s*\d+\b",
            f"{evidence_fact.winner_goals}-{evidence_fact.loser_goals}",
            claim_text,
            count=1,
        )

        if corrected_claim == claim_text:
            corrected_claim = (
                f"{winner} beat {loser} "
                f"{evidence_fact.winner_goals}-{evidence_fact.loser_goals}."
            )

        return (
            corrected_claim,
            claim_fact.score_text,
            f"{evidence_fact.winner_goals}-{evidence_fact.loser_goals}",
        )

    return None


def extract_score_fact(text: str) -> ScoreFact | None:
    score_match = re.search(r"\b(\d+)\s*[-–]\s*(\d+)\b", text)
    if score_match is None:
        return None

    first_goals = int(score_match.group(1))
    second_goals = int(score_match.group(2))
    score_text = score_match.group(0)

    winner, loser = _extract_winner_loser(text)
    if winner is None or loser is None:
        return None

    if first_goals == second_goals:
        return None

    winner_goals = max(first_goals, second_goals)
    loser_goals = min(first_goals, second_goals)

    return ScoreFact(
        winner=_normalize_team(winner),
        loser=_normalize_team(loser),
        winner_goals=winner_goals,
        loser_goals=loser_goals,
        score_text=score_text,
    )


def _extract_winner_loser(text: str) -> tuple[str | None, str | None]:
    score_between_teams = re.search(
        rf"\b({TEAM_PATTERN})\s+(\d+)\s*[-–]\s*(\d+)\s+({TEAM_PATTERN})(?:\s|,|\.|\||$)",
        text,
    )
    if score_between_teams is not None:
        first = _clean_team(score_between_teams.group(1))
        second = _clean_team(score_between_teams.group(4))
        first_goals = int(score_between_teams.group(2))
        second_goals = int(score_between_teams.group(3))
        if first_goals > second_goals:
            return first, second
        if second_goals > first_goals:
            return second, first

    teams_then_score = re.search(
        rf"\b({TEAM_PATTERN})\s+(?i:v|vs\.?|versus)\s+({TEAM_PATTERN})\s+(\d+)\s*[-–]\s*(\d+)\b",
        text,
    )
    if teams_then_score is not None:
        first = _clean_team(teams_then_score.group(1))
        second = _clean_team(teams_then_score.group(2))
        first_goals = int(teams_then_score.group(3))
        second_goals = int(teams_then_score.group(4))
        if first_goals > second_goals:
            return first, second
        if second_goals > first_goals:
            return second, first

    patterns = [
        rf"\b({TEAM_PATTERN})\s+(?i:beat|beats|defeated|defeats)\s+(?:the\s+)?({TEAM_PATTERN})(?:\s|,|\.|$)",
        rf"\b({TEAM_PATTERN})\s+(?i:lost)\s+(?i:to)\s+(?:the\s+)?({TEAM_PATTERN}).*?\d+\s*[-–]\s*\d+\s+(?i:win|victory)(?:\s|,|\.|$)",
        rf"\b({TEAM_PATTERN})(?:'s)?\s+\d+\s*[-–]\s*\d+\s+(?i:victory over)\s+(?:the\s+)?({TEAM_PATTERN})(?:\s|,|\.|$)",
        rf"\b({TEAM_PATTERN})\s+(?i:lost)\s+\d+\s*[-–]\s*\d+\s+(?i:to)\s+(?:the\s+)?({TEAM_PATTERN})(?:\s|,|\.|$)",
        rf"\b({TEAM_PATTERN}).*?\d+\s*[-–]\s*\d+\s+(?i:loss to)\s+(?:the\s+)?({TEAM_PATTERN})(?:\s|,|\.|$)",
    ]

    for index, pattern in enumerate(patterns):
        match = re.search(pattern, text)
        if match is None:
            continue

        first = _clean_team(match.group(1))
        second = _clean_team(match.group(2))

        if index in {1, 3, 4}:
            return second, first

        return first, second

    return None, None


def _same_matchup(left: ScoreFact, right: ScoreFact) -> bool:
    left_teams = {left.winner, left.loser}
    right_teams = {right.winner, right.loser}
    return None not in left_teams and left_teams == right_teams


def _clean_team(value: str) -> str:
    cleaned = re.sub(r"(?i)'s$", "", value)
    return re.sub(r"\s+", " ", cleaned.replace(".", " ")).strip(" ,.'")


def _normalize_team(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = re.sub(r"[^a-zA-Z0-9]+", " ", value.lower()).strip()
    normalized = TEAM_ALIASES.get(normalized, normalized)

    return normalized or None


def _display_team(value: str | None) -> str | None:
    if value is None:
        return None
    if value == "usa":
        return "USA"
    return " ".join(part.capitalize() for part in value.split())
