import json

from app.providers.llm.base import LLMProvider
from app.schemas.llm import LLMRequest, LLMResponse


class DevDeterministicLLMProvider(LLMProvider):
    """Local-development deterministic LLM replacement.

    This is intentionally narrow. It exists to keep local pipeline tests moving
    when the real LLM is unavailable. It should not be used as production
    evidence or production verification logic.
    """

    name = "dev_deterministic_llm_provider"

    def generate(self, request: LLMRequest) -> LLMResponse:
        prompt = self._prompt_text(request)
        normalized = prompt.lower()

        if self._looks_like_stance_prompt(normalized):
            content = self._stance_response(normalized)
        elif "create a retrieval plan" in normalized:
            content = self._search_plan_response(normalized)
        elif "decompose" in normalized or "atomic claim" in normalized:
            content = self._claim_decomposition_response(normalized)
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

    def _looks_like_stance_prompt(self, prompt: str) -> bool:
        stance_markers = [
            "stance",
            "supports",
            "contradicts",
            "insufficient",
            "claim:",
            "evidence:",
        ]

        return (
            "claim" in prompt
            and "evidence" in prompt
            and any(marker in prompt for marker in stance_markers)
        )

    def _prompt_text(self, request: LLMRequest) -> str:
        return "\n".join(message.content for message in request.messages)

    def _claim_decomposition_response(self, prompt: str) -> str:
        claim_text = self._extract_after(prompt, "claim text:")
        if not claim_text:
            claim_text = self._extract_after(prompt, "input text:")
        if not claim_text:
            claim_text = "The Boston Celtics won the 2024 NBA Finals."

        payload = {
            "claims": [
                {
                    "claim_text": claim_text.strip(),
                    "claim_type": "event",
                    "subject": "The Boston Celtics",
                    "predicate": "won",
                    "object": "the 2024 NBA Finals",
                    "event_time": None,
                    "confidence": 1.0,
                }
            ]
        }

        return json.dumps(payload)

    def _search_plan_response(self, prompt: str) -> str:
        payload = {
            "source_candidates": [
                {
                    "name": "NBA official website",
                    "domain": "nba.com",
                    "url": None,
                    "expected_source_type": "official",
                    "rationale": "Official league source for NBA results and Finals coverage.",
                    "priority": 1,
                },
                {
                    "name": "ESPN NBA coverage",
                    "domain": "espn.com",
                    "url": None,
                    "expected_source_type": "trusted_media",
                    "rationale": "Trusted sports media source for NBA Finals reporting.",
                    "priority": 2,
                },
            ],
            "queries": [
                {
                    "query": "2024 NBA Finals winner Boston Celtics",
                    "purpose": "Find official confirmation that Boston won the 2024 NBA Finals.",
                    "cost_tier": "free",
                    "expected_source_type": "official",
                    "target_domains": ["nba.com"],
                    "provider": "configured_free_provider",
                },
                {
                    "query": "Boston Celtics won 2024 NBA Finals",
                    "purpose": "Find corroborating sports media reports.",
                    "cost_tier": "free",
                    "expected_source_type": "trusted_media",
                    "target_domains": ["espn.com"],
                    "provider": "configured_free_provider",
                },
            ],
            "should_use_paid_search": False,
            "paid_search_rationale": "Development fallback avoids paid search.",
            "max_paid_search_calls": 0,
        }

        return json.dumps(payload)

    def _stance_response(self, prompt: str) -> str:
        normalized = prompt.lower()

        has_celtics = "boston celtics" in normalized or "celtics" in normalized
        has_finals = "2024 nba finals" in normalized or "nba finals" in normalized

        support_terms = [
            "won",
            "win",
            "winner",
            "champion",
            "champions",
            "championship",
            "defeated",
            "beat",
            "captured",
            "clinched",
            "title",
            "finals",
            "mavericks",
        ]

        contradiction_terms = [
            "lost",
            "did not win",
            "failed to win",
            "runner-up",
        ]

        has_contradiction_signal = any(term in normalized for term in contradiction_terms)
        has_support_signal = any(term in normalized for term in support_terms)

        if has_celtics and has_finals and has_contradiction_signal:
            payload = {
                "stance": "contradicts",
                "stance_label": "contradicts",
                "label": "contradicts",
                "confidence": 0.88,
                "reason": "Development fallback: the evidence context contains Celtics and NBA Finals language with a contradiction signal.",
                "rationale": "Development fallback: the evidence context contains Celtics and NBA Finals language with a contradiction signal.",
                "rationale": "Development fallback: the evidence context contains Celtics and NBA Finals language with a contradiction signal.",
            }
        elif has_celtics and has_finals and has_support_signal:
            payload = {
                "stance": "supports",
                "stance_label": "supports",
                "label": "supports",
                "confidence": 0.92,
                "reason": "Development fallback: the evidence context mentions the Celtics, the NBA Finals, and a win/championship signal.",
                "rationale": "Development fallback: the evidence context mentions the Celtics, the NBA Finals, and a win/championship signal.",
                "rationale": "Development fallback: the evidence context mentions the Celtics, the NBA Finals, and a win/championship signal.",
            }
        else:
            payload = {
                "stance": "insufficient",
                "stance_label": "insufficient",
                "label": "insufficient",
                "confidence": 0.8,
                "reason": "Development fallback: the evidence context does not contain enough specific support signal.",
                "rationale": "Development fallback: the evidence context does not contain enough specific support signal.",
                "rationale": "Development fallback: the evidence context does not contain enough specific support signal.",
            }

        return json.dumps(payload)

    def _extract_after(self, prompt: str, marker: str) -> str | None:
        index = prompt.find(marker)
        if index == -1:
            return None

        value = prompt[index + len(marker):].strip().splitlines()[0].strip()
        return value or None
