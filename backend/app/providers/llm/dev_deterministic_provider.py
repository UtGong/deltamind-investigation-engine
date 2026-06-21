import json
import re

from app.providers.llm.base import LLMProvider
from app.schemas.llm import LLMRequest, LLMResponse


class DevDeterministicLLMProvider(LLMProvider):
    name = "dev_deterministic_llm_provider"

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

        subject = self._extract_subject_from_claim(claim_text)
        object_text = self._extract_object_from_claim(claim_text)

        payload = {
            "claims": [
                {
                    "claim_text": claim_text,
                    "claim_type": "event",
                    "subject": subject,
                    "predicate": "won",
                    "object": object_text,
                    "event_time": None,
                    "confidence": 1.0,
                }
            ]
        }

        return json.dumps(payload)

    def _search_plan_response(self, prompt: str) -> str:
        claim_text = self._extract_claim_from_prompt(prompt)
        subject = self._extract_subject_from_claim(claim_text)

        queries = [
            f"{subject} won 2024 NBA Finals",
            f"2024 NBA Finals winner {subject}",
            "2024 NBA Finals Celtics Mavericks winner",
        ]

        payload = {
            "source_candidates": [
                {
                    "name": "NBA official website",
                    "domain": "nba.com",
                    "url": None,
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
            "reasoning": "Use official and trusted sports sources to verify the 2024 NBA Finals winner.",
        }

        return json.dumps(payload)

    def _stance_response(self, prompt: str) -> str:
        claim_text = self._extract_section(
            prompt,
            start_markers=["CLAIM:", "Claim:", "claim:"],
            end_markers=["EVIDENCE TITLE:", "Evidence Title:", "evidence title:", "EVIDENCE:", "Evidence:", "evidence:"],
        )

        evidence_title = self._extract_section(
            prompt,
            start_markers=["EVIDENCE TITLE:", "Evidence Title:", "evidence title:"],
            end_markers=["EVIDENCE TEXT:", "Evidence Text:", "evidence text:"],
        )

        evidence_text = self._extract_section(
            prompt,
            start_markers=["EVIDENCE TEXT:", "Evidence Text:", "evidence text:", "EVIDENCE:", "Evidence:", "evidence:"],
            end_markers=[],
        )

        combined_evidence = f"{evidence_title}\n{evidence_text}".lower()
        normalized_title = evidence_title.lower()
        claim_subject = self._extract_subject_from_claim(claim_text).lower()

        is_search_result_page = (
            " search" in normalized_title
            or normalized_title.endswith("search")
            or "found results for" in combined_evidence
            or "/search/" in combined_evidence
        )

        if is_search_result_page:
            payload = self._stance_payload(
                "insufficient",
                0.88,
                "Development fallback: search result pages are not treated as factual evidence.",
            )
            return json.dumps(payload)

        evidence_says_celtics_won = self._evidence_says_celtics_won(combined_evidence)
        evidence_says_mavericks_won = self._evidence_says_mavericks_won(combined_evidence)

        if "boston celtics" in claim_subject or claim_subject == "celtics":
            if evidence_says_celtics_won:
                payload = self._stance_payload(
                    "supports",
                    0.92,
                    "Development fallback: evidence indicates the Boston Celtics won the 2024 NBA Finals.",
                )
            elif evidence_says_mavericks_won:
                payload = self._stance_payload(
                    "contradicts",
                    0.9,
                    "Development fallback: evidence indicates the Mavericks, not the Celtics, won.",
                )
            else:
                payload = self._stance_payload(
                    "insufficient",
                    0.8,
                    "Development fallback: evidence does not clearly identify the Finals winner.",
                )

        elif "dallas mavericks" in claim_subject or claim_subject == "mavericks":
            if evidence_says_celtics_won:
                payload = self._stance_payload(
                    "contradicts",
                    0.92,
                    "Development fallback: evidence indicates the Boston Celtics, not the Dallas Mavericks, won the 2024 NBA Finals.",
                )
            elif evidence_says_mavericks_won:
                payload = self._stance_payload(
                    "supports",
                    0.9,
                    "Development fallback: evidence indicates the Dallas Mavericks won.",
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
        lines = [line.strip() for line in prompt.splitlines() if line.strip()]

        for line in lines:
            lower = line.lower()
            if lower.startswith("claim:"):
                return line.split(":", 1)[1].strip()

        finals_match = re.search(
            r"((?:the\s+)?(?:boston celtics|dallas mavericks|celtics|mavericks)\s+won\s+the\s+2024\s+nba\s+finals\.?)",
            prompt,
            flags=re.IGNORECASE,
        )

        if finals_match:
            claim = finals_match.group(1).strip()
            if not claim.lower().startswith("the "):
                claim = "The " + claim
            return claim

        return "The Boston Celtics won the 2024 NBA Finals."

    def _extract_subject_from_claim(self, claim_text: str) -> str:
        normalized = claim_text.lower()

        if "dallas mavericks" in normalized:
            return "The Dallas Mavericks"
        if "mavericks" in normalized:
            return "The Dallas Mavericks"
        if "boston celtics" in normalized:
            return "The Boston Celtics"
        if "celtics" in normalized:
            return "The Boston Celtics"

        match = re.search(r"the\s+(.+?)\s+won\s+", claim_text, flags=re.IGNORECASE)
        if match:
            return "The " + match.group(1).strip()

        return "The Boston Celtics"

    def _extract_object_from_claim(self, claim_text: str) -> str:
        normalized = claim_text.lower()

        if "2024 nba finals" in normalized:
            return "the 2024 NBA Finals"

        return "the claimed event"

    def _evidence_says_celtics_won(self, evidence: str) -> bool:
        celtics_markers = [
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
        ]

        return any(marker in evidence for marker in celtics_markers)

    def _evidence_says_mavericks_won(self, evidence: str) -> bool:
        mavericks_markers = [
            "mavericks clinch",
            "mavericks win",
            "mavericks won",
            "dallas mavericks won",
            "dallas mavericks defeated",
            "mavericks defeated the boston celtics",
        ]

        return any(marker in evidence for marker in mavericks_markers)

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
