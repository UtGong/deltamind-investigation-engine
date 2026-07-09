import json
import re

from pydantic import BaseModel

from app.agents.base import Agent
from app.agents.round_facts import extract_round_fact, infer_round_stance
from app.agents.score_facts import extract_score_fact, infer_score_stance
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
        deterministic_output = self._score_stance_output(input_data)
        if deterministic_output is not None:
            return deterministic_output

        deterministic_output = self._round_stance_output(input_data)
        if deterministic_output is not None:
            return deterministic_output

        score_fallback_output = self._score_claim_fallback_output(input_data)
        if score_fallback_output is not None:
            return score_fallback_output

        round_fallback_output = self._round_claim_fallback_output(input_data)
        if round_fallback_output is not None:
            return round_fallback_output

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

        try:
            response = self.llm_provider.generate(request)
            payload = self._safe_json_loads(response.content)
            fallback_reason = None
        except Exception as error:
            response = LLMResponse(
                content="",
                provider=getattr(self.llm_provider, "name", "unknown_llm_provider"),
                model="fallback_local_stance",
                input_tokens=0,
                output_tokens=0,
                estimated_cost_usd=0.0,
                metadata={
                    "fallback_used": True,
                    "fallback_reason": "llm_provider_error",
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                },
            )
            payload = None
            fallback_reason = (
                "Fallback stance classification was used because the LLM provider "
                f"failed with {type(error).__name__}: {error}."
            )

        if payload is None:
            stance_label = self._fallback_stance(input_data)
            confidence = self._fallback_confidence(stance_label)
            rationale = fallback_reason or (
                "Fallback stance classification was used because the LLM response "
                "was not valid stance JSON."
            )
        else:
            stance_label = self._parse_stance_label(payload.get("stance_label"))
            confidence = self._parse_confidence(payload.get("confidence"))
            rationale = str(payload.get("rationale") or "").strip()

            if not rationale:
                rationale = "The stance was classified from the provided evidence text."

        score_stance = infer_score_stance(
            claim_text=input_data.claim.claim_text,
            evidence_text=f"{input_data.evidence.title or ''}\n{input_data.evidence.evidence_text}",
        )
        if score_stance == "supports":
            stance_label = StanceLabel.SUPPORTS
            confidence = max(confidence, 0.88)
            rationale = "The evidence states the same match winner and score as the claim."
        elif score_stance == "contradicts":
            stance_label = StanceLabel.CONTRADICTS
            confidence = max(confidence, 0.9)
            rationale = "The evidence states the same matchup with a different score."

        round_stance = infer_round_stance(
            claim_text=input_data.claim.claim_text,
            evidence_text=f"{input_data.evidence.title or ''}\n{input_data.evidence.evidence_text}",
        )
        if round_stance == "supports":
            stance_label = StanceLabel.SUPPORTS
            confidence = max(confidence, 0.88)
            rationale = "The evidence states the same event round as the claim."
        elif round_stance == "contradicts":
            stance_label = StanceLabel.CONTRADICTS
            confidence = max(confidence, 0.9)
            rationale = "The evidence states the same event with a different round."

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

    def _score_stance_output(self, input_data: LLMStanceInput) -> LLMStanceOutput | None:
        score_stance = infer_score_stance(
            claim_text=input_data.claim.claim_text,
            evidence_text=f"{input_data.evidence.title or ''}\n{input_data.evidence.evidence_text}",
        )

        if score_stance == "supports":
            stance_label = StanceLabel.SUPPORTS
            confidence = 0.88
            rationale = "The evidence states the same match winner and score as the claim."
        elif score_stance == "contradicts":
            stance_label = StanceLabel.CONTRADICTS
            confidence = 0.9
            rationale = "The evidence states the same matchup with a different score."
        else:
            return None

        return LLMStanceOutput(
            stance=self._make_stance_result(
                claim=input_data.claim,
                evidence=input_data.evidence,
                stance_label=stance_label,
                confidence=confidence,
                rationale=rationale,
            ),
            raw_response=LLMResponse(
                content="",
                provider="internal_deterministic",
                model="score-fact-stance-v1",
                input_tokens=0,
                output_tokens=0,
                estimated_cost_usd=0.0,
                metadata={"llm_used": False, "deterministic_score_stance": score_stance},
            ),
        )

    def _round_stance_output(self, input_data: LLMStanceInput) -> LLMStanceOutput | None:
        round_stance = infer_round_stance(
            claim_text=input_data.claim.claim_text,
            evidence_text=f"{input_data.evidence.title or ''}\n{input_data.evidence.evidence_text}",
        )

        if round_stance == "supports":
            stance_label = StanceLabel.SUPPORTS
            confidence = 0.88
            rationale = "The evidence states the same event round as the claim."
        elif round_stance == "contradicts":
            stance_label = StanceLabel.CONTRADICTS
            confidence = 0.9
            rationale = "The evidence states the same event with a different round."
        else:
            return None

        return LLMStanceOutput(
            stance=self._make_stance_result(
                claim=input_data.claim,
                evidence=input_data.evidence,
                stance_label=stance_label,
                confidence=confidence,
                rationale=rationale,
            ),
            raw_response=LLMResponse(
                content="",
                provider="internal_deterministic",
                model="round-fact-stance-v1",
                input_tokens=0,
                output_tokens=0,
                estimated_cost_usd=0.0,
                metadata={"llm_used": False, "deterministic_round_stance": round_stance},
            ),
        )

    def _score_claim_fallback_output(self, input_data: LLMStanceInput) -> LLMStanceOutput | None:
        if (
            extract_score_fact(input_data.claim.claim_text) is None
            and re.search(r"\b\d+\s*[-–]\s*\d+\b", input_data.claim.claim_text) is None
        ):
            return None

        stance_label = self._fallback_stance(input_data)
        confidence = min(self._fallback_confidence(stance_label), 0.5)

        return LLMStanceOutput(
            stance=self._make_stance_result(
                claim=input_data.claim,
                evidence=input_data.evidence,
                stance_label=stance_label,
                confidence=confidence,
                rationale=(
                    "Local score-claim fallback was used because the evidence did "
                    "not state a comparable score for the same matchup."
                ),
            ),
            raw_response=LLMResponse(
                content="",
                provider="internal_deterministic",
                model="score-claim-fallback-stance-v1",
                input_tokens=0,
                output_tokens=0,
                estimated_cost_usd=0.0,
                metadata={
                    "llm_used": False,
                    "fallback_reason": "score_claim_without_comparable_score_evidence",
                },
            ),
        )

    def _round_claim_fallback_output(self, input_data: LLMStanceInput) -> LLMStanceOutput | None:
        if extract_round_fact(input_data.claim.claim_text) is None:
            return None

        stance_label = self._fallback_stance(input_data)
        confidence = min(self._fallback_confidence(stance_label), 0.5)

        return LLMStanceOutput(
            stance=self._make_stance_result(
                claim=input_data.claim,
                evidence=input_data.evidence,
                stance_label=stance_label,
                confidence=confidence,
                rationale=(
                    "Local round-claim fallback was used because the evidence did "
                    "not state a comparable round value."
                ),
            ),
            raw_response=LLMResponse(
                content="",
                provider="internal_deterministic",
                model="round-claim-fallback-stance-v1",
                input_tokens=0,
                output_tokens=0,
                estimated_cost_usd=0.0,
                metadata={
                    "llm_used": False,
                    "fallback_reason": "round_claim_without_comparable_round_evidence",
                },
            ),
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

    def _fallback_confidence(self, stance_label: StanceLabel) -> float:
        if stance_label == StanceLabel.SUPPORTS:
            return 0.72
        if stance_label == StanceLabel.PARTIALLY_SUPPORTS:
            return 0.55
        if stance_label == StanceLabel.IRRELEVANT:
            return 0.45
        return 0.35

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
