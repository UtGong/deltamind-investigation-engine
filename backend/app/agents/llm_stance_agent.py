import json
import re

from pydantic import BaseModel

from app.agents.base import Agent
from app.core.constants import StanceLabel
from app.providers.llm.base import LLMProvider
from app.providers.llm.mock_provider import MockLLMProvider
from app.schemas.agent import AtomicClaim, EvidenceItem, StanceResult
from app.schemas.llm import LLMMessage, LLMRequest, LLMResponse


class LLMStanceInput(BaseModel):
    claim: AtomicClaim
    evidence: EvidenceItem


class LLMStanceOutput(BaseModel):
    stance: StanceResult
    raw_response: LLMResponse


class LLMStanceAgent(Agent[LLMStanceInput, LLMStanceOutput]):
    name = "llm_stance_agent"

    def __init__(self, llm_provider: LLMProvider | None = None) -> None:
        self.llm_provider = llm_provider or MockLLMProvider()

    def run(self, input_data: LLMStanceInput) -> LLMStanceOutput:
        request = LLMRequest(
            messages=[
                LLMMessage(
                    role="system",
                    content=(
                        "You are a stance classification agent for a fact verification system. "
                        "Classify whether the EVIDENCE supports, contradicts, partially supports, "
                        "is irrelevant to, or is insufficient for the CLAIM. "
                        "Use only the provided evidence text. Do not use world knowledge, memory, "
                        "or unstated assumptions. Return valid JSON only."
                    ),
                ),
                LLMMessage(
                    role="user",
                    content=(
                        "Classify the stance of the evidence toward the claim.\n\n"
                        "Allowed stance_label values:\n"
                        "- supports\n"
                        "- contradicts\n"
                        "- partially_supports\n"
                        "- irrelevant\n"
                        "- insufficient\n\n"
                        "Return exactly this JSON object shape:\n"
                        "{\n"
                        '  "stance_label": "supports",\n'
                        '  "confidence": 0.85,\n'
                        '  "rationale": "short explanation grounded only in the evidence"\n'
                        "}\n\n"
                        f"CLAIM:\n{input_data.claim.claim_text}\n\n"
                        f"EVIDENCE TITLE:\n{input_data.evidence.title}\n\n"
                        f"EVIDENCE TEXT:\n{input_data.evidence.evidence_text}"
                    ),
                ),
            ],
            temperature=0.0,
            response_format="json",
        )

        response = self.llm_provider.generate(request)
        payload = self._safe_json_loads(response.content)

        if payload is None:
            stance_label = self._fallback_stance(input_data)
            confidence = 0.35
            rationale = (
                "Fallback stance classification was used because the LLM response "
                "was not valid stance JSON."
            )
        else:
            stance_label = self._parse_stance_label(payload.get("stance_label"))
            confidence = self._parse_confidence(payload.get("confidence"))
            rationale = str(payload.get("rationale") or "").strip()

            if not rationale:
                rationale = "The stance was classified from the provided evidence text."

        stance = self._make_stance_result(
            claim=input_data.claim,
            evidence=input_data.evidence,
            stance_label=stance_label,
            confidence=confidence,
            rationale=rationale,
        )

        return LLMStanceOutput(
            stance=stance,
            raw_response=response,
        )

    def _safe_json_loads(self, content: str) -> dict | None:
        cleaned = content.strip()

        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()

        try:
            payload = json.loads(cleaned)
            return payload if isinstance(payload, dict) else None
        except json.JSONDecodeError:
            pass

        object_match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if object_match:
            try:
                payload = json.loads(object_match.group(0))
                return payload if isinstance(payload, dict) else None
            except json.JSONDecodeError:
                return None

        return None

    def _parse_stance_label(self, value: object) -> StanceLabel:
        normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")

        aliases = {
            "support": StanceLabel.SUPPORTS,
            "supports": StanceLabel.SUPPORTS,
            "supported": StanceLabel.SUPPORTS,
            "contradict": StanceLabel.CONTRADICTS,
            "contradicts": StanceLabel.CONTRADICTS,
            "contradicted": StanceLabel.CONTRADICTS,
            "partially_supports": StanceLabel.PARTIALLY_SUPPORTS,
            "partial_support": StanceLabel.PARTIALLY_SUPPORTS,
            "partially_supported": StanceLabel.PARTIALLY_SUPPORTS,
            "irrelevant": StanceLabel.IRRELEVANT,
            "not_relevant": StanceLabel.IRRELEVANT,
            "insufficient": StanceLabel.INSUFFICIENT,
            "not_enough_information": StanceLabel.INSUFFICIENT,
        }

        return aliases.get(normalized, StanceLabel.INSUFFICIENT)

    def _parse_confidence(self, value: object) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.5

        return max(0.0, min(1.0, confidence))

    def _fallback_stance(self, input_data: LLMStanceInput) -> StanceLabel:
        claim_text = input_data.claim.claim_text.lower()
        evidence_text = input_data.evidence.evidence_text.lower()

        if claim_text and claim_text in evidence_text:
            return StanceLabel.SUPPORTS

        claim_tokens = self._tokens(claim_text)
        evidence_tokens = self._tokens(evidence_text)

        if not claim_tokens or not evidence_tokens:
            return StanceLabel.INSUFFICIENT

        overlap = len(claim_tokens.intersection(evidence_tokens)) / len(claim_tokens)

        if overlap >= 0.8:
            return StanceLabel.PARTIALLY_SUPPORTS

        if overlap >= 0.4:
            return StanceLabel.IRRELEVANT

        return StanceLabel.INSUFFICIENT

    def _tokens(self, text: str) -> set[str]:
        stopwords = {
            "a",
            "an",
            "and",
            "are",
            "as",
            "at",
            "be",
            "by",
            "for",
            "from",
            "has",
            "have",
            "in",
            "is",
            "it",
            "of",
            "on",
            "or",
            "that",
            "the",
            "to",
            "was",
            "were",
            "with",
        }

        tokens = {
            token.lower()
            for token in re.findall(r"[a-zA-Z0-9]+", text)
        }

        return {token for token in tokens if token not in stopwords}

    def _make_stance_result(
        self,
        claim: AtomicClaim,
        evidence: EvidenceItem,
        stance_label: StanceLabel,
        confidence: float,
        rationale: str,
    ) -> StanceResult:
        fields = StanceResult.model_fields
        data = {}

        if "claim_id" in fields:
            data["claim_id"] = claim.claim_id

        if "evidence_id" in fields:
            data["evidence_id"] = evidence.evidence_id

        if "stance" in fields:
            data["stance"] = stance_label
        elif "stance_label" in fields:
            data["stance_label"] = stance_label
        elif "label" in fields:
            data["label"] = stance_label

        if "confidence" in fields:
            data["confidence"] = confidence

        if "rationale" in fields:
            data["rationale"] = rationale
        elif "reason" in fields:
            data["reason"] = rationale
        elif "explanation" in fields:
            data["explanation"] = rationale

        return StanceResult.model_validate(data)
