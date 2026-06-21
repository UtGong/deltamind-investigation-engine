import json
import re

from app.providers.llm.base import LLMProvider
from app.schemas.llm import LLMRequest, LLMResponse


class DevDeterministicLLMProvider(LLMProvider):
    name = "dev_deterministic_llm_provider"

    FINALS_FIXTURES = {
        "2024": {
            "winner": "boston celtics",
            "loser": "dallas mavericks",
            "object": "the 2024 NBA Finals",
            "winner_display": "The Boston Celtics",
            "loser_display": "The Dallas Mavericks",
            "support_markers": [
                "celtics clinch banner 18",
                "secure boston's nba-record 18th championship",
                "boston's nba-record 18th championship",
                "celtics defeated the dallas mavericks",
                "celtics beat the dallas mavericks",
                "celtics win",
                "celtics won",
                "boston celtics won",
                "boston celtics defeated",
                "nba finals 1 celtics",
            ],
        },
        "2023": {
            "winner": "denver nuggets",
            "loser": "miami heat",
            "object": "the 2023 NBA Finals",
            "winner_display": "The Denver Nuggets",
            "loser_display": "The Miami Heat",
            "support_markers": [
                "nuggets win first nba championship",
                "denver nuggets win first nba championship",
                "nuggets won their first nba championship",
                "denver nuggets won their first nba championship",
                "nuggets defeated the miami heat",
                "nuggets beat the miami heat",
                "denver defeated miami",
                "denver nuggets defeated",
                "nba finals 1 nuggets",
                "2023 nba finals",
                "nuggets",
                "miami heat",
                "nikola jokic",
                "finals mvp nikola jokic",
                "first championship",
                "first nba championship",
                "denver's first nba championship",
                "denver nuggets championship",
                "nuggets championship",
            ],
        },
    }

    UNVERIFIABLE_MARKERS = [
        "secret injury",
        "rigged",
        "unnamed official",
        "unnamed source",
        "secretly caused",
        "conspiracy",
    ]

    def generate(self, request: LLMRequest) -> LLMResponse:
        prompt = self._prompt_text(request)
        normalized = prompt.lower()

        if self._looks_like_stance_prompt(normalized):
            content = self._stance_response(prompt)
        elif "create a retrieval plan" in normalized or "retrieval plan" in normalized:
            content = self._search_plan_response(prompt)
        elif "decompose" in normalized or "atomic claim" in normalized or "claim decomposition" in normalized:
            content = self._claim_decomposition_response(prompt)
        else:
            content = "{}"

        return LLMResponse(
            content=content,
            provider=self.name,
            model="dev-deterministic",
            input_tokens=0,
            output_tokens=0,
            estimated_cost_usd=0.0,
        )

    def _prompt_text(self, request: LLMRequest) -> str:
        return "\n".join(message.content for message in request.messages)

    def _looks_like_stance_prompt(self, prompt: str) -> bool:
        stance_markers = [
            "stance",
            "classify",
            "relationship",
            "supports",
            "contradicts",
            "insufficient",
            "evidence:",
            "evidence text:",
        ]

        return (
            "claim" in prompt
            and "evidence" in prompt
            and any(marker in prompt for marker in stance_markers)
        )

    def _claim_decomposition_response(self, prompt: str) -> str:
        claim_text = self._extract_claim_from_prompt(prompt)
        fixture_year = self._extract_finals_year(claim_text)
        subject = self._extract_subject_from_claim(claim_text)

        claim_type = "event"
        predicate = "won"
        object_text = self._extract_object_from_claim(claim_text)

        if self._is_unverifiable_style_claim(claim_text):
            claim_type = "causal" if "caused" in claim_text.lower() else "unknown"
            predicate = "alleges"

        payload = {
            "claims": [
                {
                    "claim_text": claim_text,
                    "claim_type": claim_type,
                    "subject": subject,
                    "predicate": predicate,
                    "object": object_text or self._fixture_object(fixture_year),
                    "event_time": None,
                    "confidence": 1.0,
                }
            ]
        }

        return json.dumps(payload)

    def _search_plan_response(self, prompt: str) -> str:
        claim_text = self._extract_claim_from_prompt(prompt)
        fixture_year = self._extract_finals_year(claim_text) or "2024"
        subject = self._extract_subject_from_claim(claim_text)

        queries = [
            f"{subject} won {fixture_year} NBA Finals",
            f"{fixture_year} NBA Finals winner {subject}",
            f"{fixture_year} NBA Finals winner",
        ]

        nba_finals_url = f"https://www.nba.com/playoffs/{fixture_year}/nba-finals"

        payload = {
            "source_candidates": [
                {
                    "name": "NBA official Finals page",
                    "domain": "nba.com",
                    "url": nba_finals_url,
                    "source_type": "official",
                    "reason": "Official NBA source for Finals results.",
                },
                {
                    "name": "ESPN NBA coverage",
                    "domain": "espn.com",
                    "url": None,
                    "source_type": "trusted_media",
                    "reason": "Major sports media source for NBA results.",
                },
            ],
            "queries": queries,
            "search_queries": queries,
            "allow_paid_search": False,
            "reasoning": "Use official and trusted sports sources to verify the NBA Finals claim.",
        }

        return json.dumps(payload)

    def _stance_response(self, prompt: str) -> str:
        claim_text = self._extract_section(
            prompt,
            start_markers=["CLAIM:", "Claim:", "claim:"],
            end_markers=[
                "EVIDENCE TITLE:",
                "Evidence Title:",
                "evidence title:",
                "EVIDENCE:",
                "Evidence:",
                "evidence:",
            ],
        )

        evidence_title = self._extract_section(
            prompt,
            start_markers=["EVIDENCE TITLE:", "Evidence Title:", "evidence title:"],
            end_markers=["EVIDENCE TEXT:", "Evidence Text:", "evidence text:"],
        )

        evidence_text = self._extract_section(
            prompt,
            start_markers=[
                "EVIDENCE TEXT:",
                "Evidence Text:",
                "evidence text:",
                "EVIDENCE:",
                "Evidence:",
                "evidence:",
            ],
            end_markers=[],
        )

        combined_evidence = f"{evidence_title}\n{evidence_text}".lower()
        normalized_title = evidence_title.lower()
        normalized_claim = claim_text.lower()

        if self._is_search_result_page(normalized_title, combined_evidence):
            return json.dumps(
                self._stance_payload(
                    "insufficient",
                    0.88,
                    "Development fallback: search result pages are not treated as factual evidence.",
                )
            )

        if self._is_unverifiable_style_claim(normalized_claim):
            return json.dumps(
                self._stance_payload(
                    "insufficient",
                    0.9,
                    "Development fallback: causal, secret, or rigging allegations require direct evidence; generic result evidence is insufficient.",
                )
            )

        fixture_year = self._extract_finals_year(normalized_claim)
        if fixture_year not in self.FINALS_FIXTURES:
            return json.dumps(
                self._stance_payload(
                    "insufficient",
                    0.8,
                    "Development fallback: unsupported Finals year for deterministic fixture check.",
                )
            )

        fixture = self.FINALS_FIXTURES[fixture_year]
        claim_subject = self._extract_subject_from_claim(claim_text).lower()

        evidence_says_winner_won = self._evidence_says_fixture_winner_won(
            combined_evidence,
            fixture_year,
        )

        if fixture["winner"] in claim_subject:
            if evidence_says_winner_won:
                payload = self._stance_payload(
                    "supports",
                    0.92,
                    f"Development fallback: evidence indicates {fixture['winner_display']} won {fixture['object']}.",
                )
            else:
                payload = self._stance_payload(
                    "insufficient",
                    0.8,
                    "Development fallback: evidence does not clearly identify the Finals winner.",
                )

        elif fixture["loser"] in claim_subject:
            if evidence_says_winner_won:
                payload = self._stance_payload(
                    "contradicts",
                    0.92,
                    f"Development fallback: evidence indicates {fixture['winner_display']}, not {fixture['loser_display']}, won {fixture['object']}.",
                )
            else:
                payload = self._stance_payload(
                    "insufficient",
                    0.8,
                    "Development fallback: evidence does not clearly identify the Finals winner.",
                )
        else:
            payload = self._stance_payload(
                "insufficient",
                0.8,
                "Development fallback: claim subject is not recognized for this deterministic sports fixture.",
            )

        return json.dumps(payload)

    def _stance_payload(self, label: str, confidence: float, rationale: str) -> dict:
        return {
            "stance": label,
            "stance_label": label,
            "label": label,
            "confidence": confidence,
            "reason": rationale,
            "rationale": rationale,
        }

    def _extract_claim_from_prompt(self, prompt: str) -> str:
        section_claim = self._extract_section(
            prompt,
            start_markers=["CLAIM:", "Claim:", "claim:"],
            end_markers=[
                "EVIDENCE",
                "Evidence",
                "evidence",
                "Return",
                "return",
                "Allowed",
                "allowed",
            ],
        )
        if section_claim:
            return " ".join(section_claim.split())

        explicit_patterns = [
            r"(The\s+20\d{2}\s+NBA\s+Finals\s+were\s+rigged\s+by\s+an\s+unnamed\s+official\.?)",
            r"(A\s+secret\s+injury\s+caused\s+the\s+[A-Za-z ]+\s+to\s+win\s+the\s+20\d{2}\s+NBA\s+Finals\.?)",
            r"(The\s+[A-Za-z ]+\s+won\s+the\s+20\d{2}\s+NBA\s+Finals\.?)",
        ]

        for pattern in explicit_patterns:
            match = re.search(pattern, prompt, flags=re.IGNORECASE)
            if match:
                claim = " ".join(match.group(1).strip().split())
                if not claim.endswith("."):
                    claim += "."
                return claim

        finals_match = re.search(
            r"((?:the\s+)?[a-zA-Z ]+?\s+(?:won|were rigged|was rigged|caused).+?20\d{2}\s+NBA\s+Finals\.?)",
            prompt,
            flags=re.IGNORECASE,
        )

        if finals_match:
            claim = finals_match.group(1).strip()
            if not claim.lower().startswith(("the ", "a ")):
                claim = "The " + claim
            return claim

        return "The Boston Celtics won the 2024 NBA Finals."

    def _extract_subject_from_claim(self, claim_text: str) -> str:
        normalized = claim_text.lower()

        teams = {
            "boston celtics": "The Boston Celtics",
            "celtics": "The Boston Celtics",
            "dallas mavericks": "The Dallas Mavericks",
            "mavericks": "The Dallas Mavericks",
            "denver nuggets": "The Denver Nuggets",
            "nuggets": "The Denver Nuggets",
            "miami heat": "The Miami Heat",
            "heat": "The Miami Heat",
        }

        for marker, display in teams.items():
            if marker in normalized:
                return display

        if "2024 nba finals" in normalized or "2023 nba finals" in normalized:
            return "The NBA Finals"

        match = re.search(r"the\s+(.+?)\s+won\s+", claim_text, flags=re.IGNORECASE)
        if match:
            return "The " + match.group(1).strip()

        return "The claim"

    def _extract_object_from_claim(self, claim_text: str) -> str:
        year = self._extract_finals_year(claim_text)
        return self._fixture_object(year)

    def _fixture_object(self, year: str | None) -> str:
        if year:
            return f"the {year} NBA Finals"
        return "the claimed event"

    def _extract_finals_year(self, text: str) -> str | None:
        match = re.search(r"(20\d{2})\s+NBA\s+Finals", text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    def _is_unverifiable_style_claim(self, text: str) -> bool:
        normalized = text.lower()
        return any(marker in normalized for marker in self.UNVERIFIABLE_MARKERS)

    def _is_search_result_page(self, title: str, evidence: str) -> bool:
        return (
            " search" in title
            or title.endswith("search")
            or "found results for" in evidence
            or "/search/" in evidence
        )

    def _evidence_says_fixture_winner_won(self, evidence: str, fixture_year: str) -> bool:
        fixture = self.FINALS_FIXTURES[fixture_year]

        if any(marker in evidence for marker in fixture["support_markers"]):
            return True

        winner = fixture["winner"]
        loser = fixture["loser"]

        generic_patterns = [
            f"{winner} won",
            f"{winner} defeated",
            f"{winner} beat",
            f"{winner} clinch",
            f"{winner} championship",
            f"{winner} nba champions",
            f"{winner} vs. {loser}",
        ]

        return any(pattern in evidence for pattern in generic_patterns)

    def _extract_section(
        self,
        text: str,
        start_markers: list[str],
        end_markers: list[str],
    ) -> str:
        start_index = -1
        start_marker = ""

        for marker in start_markers:
            candidate_index = text.find(marker)
            if candidate_index != -1 and (start_index == -1 or candidate_index < start_index):
                start_index = candidate_index
                start_marker = marker

        if start_index == -1:
            return ""

        section_start = start_index + len(start_marker)
        section = text[section_start:]

        end_index = -1
        for marker in end_markers:
            candidate_index = section.find(marker)
            if candidate_index != -1 and (end_index == -1 or candidate_index < end_index):
                end_index = candidate_index

        if end_index != -1:
            section = section[:end_index]

        return section.strip()
