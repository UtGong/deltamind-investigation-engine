import json
import re

from pydantic import BaseModel

from app.agents.base import Agent
from app.core.constants import ClaimType
from app.providers.llm.base import LLMProvider
from app.providers.llm.mock_provider import MockLLMProvider
from app.schemas.agent import AtomicClaim
from app.schemas.llm import LLMMessage, LLMRequest, LLMResponse


class LLMClaimDecompositionInput(BaseModel):
    case_id: str
    input_text: str


class LLMClaimDecompositionOutput(BaseModel):
    claims: list[AtomicClaim]
    raw_response: LLMResponse


class LLMClaimDecompositionAgent(
    Agent[LLMClaimDecompositionInput, LLMClaimDecompositionOutput]
):
    name = "llm_claim_decomposition_agent"

    def __init__(self, llm_provider: LLMProvider | None = None) -> None:
        self.llm_provider = llm_provider or MockLLMProvider()

    def run(self, input_data: LLMClaimDecompositionInput) -> LLMClaimDecompositionOutput:
        request = LLMRequest(
            messages=[
                LLMMessage(
                    role="system",
                    content=(
                        "You are a claim decomposition agent for an investigation system. "
                        "Extract factual, verifiable atomic claims. Return valid JSON only. "
                        "Do not include markdown. Return a JSON object, not a top-level array."
                    ),
                ),
                LLMMessage(
                    role="user",
                    content=(
                        "Extract atomic claims from the input below.\n\n"
                        "Rules:\n"
                        "1. Each atomic claim must contain exactly one verifiable factual statement.\n"
                        "2. Split compound sentences into separate claims when needed.\n"
                        "3. Ignore pure opinions, vague commentary, navigation text, ads, and boilerplate.\n"
                        "4. Preserve important dates, numbers, entities, locations, and quoted statements.\n"
                        "5. claim_type MUST be exactly one of: "
                        "event, numeric, quote, entity_relationship, transfer, injury, "
                        "schedule, result, causal, prediction, policy, historical, unknown.\n"
                        "6. Do not use generic claim_type values like fact or statement.\n"
                        "7. confidence MUST be a number from 0.0 to 1.0, not text.\n"
                        "8. If subject, predicate, or object is unclear, use null.\n\n"
                        "9. Keep dependent qualifiers such as dates, amounts, locations, sources, "
                        "rounds, scores, and context phrases attached to the factual statement they "
                        "modify. Do not split fragments like 'with 3.2 million users', 'in Paris', "
                        "'on June 10', or 'according to the filing' into standalone claims.\n\n"
                        "Return exactly this JSON object shape:\n"
                        "{\n"
                        '  "claims": [\n'
                        "    {\n"
                        '      "claim_text": "string",\n'
                        '      "claim_type": "transfer",\n'
                        '      "subject": "string or null",\n'
                        '      "predicate": "string or null",\n'
                        '      "object": "string or null",\n'
                        '      "confidence": 0.85\n'
                        "    }\n"
                        "  ]\n"
                        "}\n\n"
                        f"Input:\n{input_data.input_text}"
                    ),
                ),
            ],
            temperature=0.0,
            response_format="json",
        )

        response = self.llm_provider.generate(request)

        claims = self._parse_claims(
            case_id=input_data.case_id,
            content=response.content,
            original_input=input_data.input_text,
        )

        return LLMClaimDecompositionOutput(
            claims=claims,
            raw_response=response,
        )

    def _parse_claims(
        self,
        case_id: str,
        content: str,
        original_input: str,
    ) -> list[AtomicClaim]:
        payload = self._safe_json_loads(content)

        if payload is None:
            return self._fallback_claims(case_id, original_input)

        if isinstance(payload, dict):
            raw_claims = payload.get("claims", [])
        elif isinstance(payload, list):
            raw_claims = payload
        else:
            return self._fallback_claims(case_id, original_input)

        if not isinstance(raw_claims, list):
            return self._fallback_claims(case_id, original_input)

        claims: list[AtomicClaim] = []

        for index, raw_claim in enumerate(raw_claims, start=1):
            if not isinstance(raw_claim, dict):
                continue

            claim_text = str(raw_claim.get("claim_text") or "").strip()

            if not claim_text:
                continue

            claims.append(
                AtomicClaim(
                    claim_id=f"{case_id}_claim_{index}",
                    claim_text=claim_text,
                    claim_type=self._parse_claim_type(
                        raw_claim.get("claim_type"),
                        claim_text,
                    ),
                    subject=raw_claim.get("subject"),
                    predicate=raw_claim.get("predicate"),
                    object=raw_claim.get("object"),
                    confidence=self._parse_confidence(raw_claim.get("confidence")),
                )
            )

        if not claims:
            return self._fallback_claims(case_id, original_input)

        return self._repair_claims(case_id, original_input, claims)

    def _safe_json_loads(self, content: str) -> dict | list | None:
        cleaned = content.strip()

        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()

        try:
            payload = json.loads(cleaned)
            if isinstance(payload, (dict, list)):
                return payload
            return None
        except json.JSONDecodeError:
            pass

        object_match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if object_match:
            try:
                payload = json.loads(object_match.group(0))
                if isinstance(payload, (dict, list)):
                    return payload
            except json.JSONDecodeError:
                pass

        list_match = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
        if list_match:
            try:
                payload = json.loads(list_match.group(0))
                if isinstance(payload, (dict, list)):
                    return payload
            except json.JSONDecodeError:
                pass

        return None

    def _fallback_claims(self, case_id: str, text: str) -> list[AtomicClaim]:
        sentences = [
            item.strip()
            for item in re.split(r"(?<=[.!?])\s+|\n+", text.strip())
            if item.strip()
        ]

        if not sentences:
            sentences = [text.strip()]

        return [
            AtomicClaim(
                claim_id=f"{case_id}_claim_{index}",
                claim_text=sentence,
                claim_type=self._infer_claim_type(sentence),
                confidence=0.3,
            )
            for index, sentence in enumerate(sentences, start=1)
        ]

    def _repair_claims(
        self,
        case_id: str,
        original_input: str,
        claims: list[AtomicClaim],
    ) -> list[AtomicClaim]:
        if len(claims) <= 1:
            return claims

        repaired: list[AtomicClaim] = []
        pending_fragments: list[AtomicClaim] = []

        for claim in claims:
            if self._is_dependent_fragment(claim):
                pending_fragments.append(claim)
                continue

            if repaired and pending_fragments:
                repaired[-1] = self._merge_claim_with_fragments(
                    repaired[-1],
                    pending_fragments,
                )
                pending_fragments = []

            repaired.append(claim)

        if repaired and pending_fragments:
            repaired[-1] = self._merge_claim_with_fragments(
                repaired[-1],
                pending_fragments,
            )

        if not repaired:
            return claims

        if len(repaired) == 1 and self._is_single_statement(original_input):
            repaired[0] = repaired[0].model_copy(
                update={"claim_text": " ".join(original_input.strip().split())}
            )

        return [
            claim.model_copy(update={"claim_id": f"{case_id}_claim_{index}"})
            for index, claim in enumerate(repaired, start=1)
        ]

    def _is_dependent_fragment(self, claim: AtomicClaim) -> bool:
        text = claim.claim_text.strip()
        lowered = text.lower()

        starts_with_dependent_marker = re.match(
            r"^(with|without|in|on|at|by|from|for|during|after|before|according to|"
            r"under|over|worth|valued at|including|excluding)\b",
            lowered,
        )
        if starts_with_dependent_marker:
            return True

        has_anchor_fields = bool(claim.subject and claim.predicate)
        if has_anchor_fields:
            return False

        if self._has_statement_verb(lowered):
            return False

        mostly_context = bool(
            re.search(r"\b(?:19|20)\d{2}\b", text)
            or re.search(r"\b\d+(?:\.\d+)?\s*(?:%|million|billion|trillion|usd|dollars?)\b", lowered)
            or re.search(r"\b\d+\s*[-–]\s*\d+\b", text)
            or re.search(r"\b(?:round|quarter|q[1-4]|fiscal year|fy)\b", lowered)
        )

        return mostly_context and len(text.split()) <= 8

    def _has_statement_verb(self, lowered_text: str) -> bool:
        return bool(
            re.search(
                r"\b("
                r"is|are|was|were|be|been|being|has|have|had|"
                r"won|lost|beat|beats|defeated|defeats|joined|signed|"
                r"said|announced|reported|filed|raised|fell|rose|"
                r"acquired|sold|bought|launched|released"
                r")\b",
                lowered_text,
            )
        )

    def _is_single_statement(self, text: str) -> bool:
        cleaned = text.strip()
        if not cleaned:
            return False

        sentence_breaks = re.findall(r"[.!?]\s+", cleaned)
        return len(sentence_breaks) == 0

    def _merge_claim_with_fragments(
        self,
        claim: AtomicClaim,
        fragments: list[AtomicClaim],
    ) -> AtomicClaim:
        text_parts = [claim.claim_text, *[fragment.claim_text for fragment in fragments]]
        merged_text = " ".join(" ".join(text_parts).split())
        confidence_values = [claim.confidence, *[fragment.confidence for fragment in fragments]]

        return claim.model_copy(
            update={
                "claim_text": merged_text,
                "confidence": max(confidence_values),
            }
        )

    def _parse_claim_type(self, value: object, claim_text: str) -> ClaimType:
        if value is not None:
            normalized = str(value).strip().lower()

            if normalized in {"fact", "statement", "factual", "claim"}:
                return self._infer_claim_type(claim_text)

            try:
                return ClaimType(normalized)
            except ValueError:
                return self._infer_claim_type(claim_text)

        return self._infer_claim_type(claim_text)

    def _infer_claim_type(self, text: str) -> ClaimType:
        lowered = text.lower()

        if any(word in lowered for word in ["joined", "signed", "transfer", "traded"]):
            return ClaimType.TRANSFER

        if any(word in lowered for word in ["injured", "injury", "available", "returned"]):
            return ClaimType.INJURY

        if any(word in lowered for word in ["won", "lost", "beat", "defeated", "score"]):
            return ClaimType.RESULT

        if any(word in lowered for word in ["schedule", "match date"]):
            return ClaimType.SCHEDULE

        if re.search(r"\b\d+(?:\.\d+)?%?\b", lowered):
            return ClaimType.NUMERIC

        return ClaimType.UNKNOWN

    def _parse_confidence(self, value: object) -> float:
        if isinstance(value, str):
            normalized = value.strip().lower()

            text_confidence = {
                "very high": 0.95,
                "high": 0.9,
                "medium": 0.6,
                "moderate": 0.6,
                "low": 0.3,
                "very low": 0.15,
            }

            if normalized in text_confidence:
                return text_confidence[normalized]

        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.0

        return max(0.0, min(1.0, confidence))
