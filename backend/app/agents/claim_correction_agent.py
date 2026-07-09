import json
import re

from pydantic import BaseModel, Field

from app.agents.base import Agent
from app.agents.score_facts import build_score_correction
from app.providers.llm.base import LLMProvider
from app.providers.llm.mock_provider import MockLLMProvider
from app.schemas.agent import AtomicClaim, EvidenceItem, PivotVerdict, StanceResult
from app.schemas.correction import ClaimCorrection, ClaimCorrectionChange
from app.schemas.llm import LLMMessage, LLMRequest, LLMResponse


class ClaimCorrectionInput(BaseModel):
    claim: AtomicClaim
    evidence: list[EvidenceItem] = Field(default_factory=list)
    stances: list[StanceResult] = Field(default_factory=list)
    verdict: PivotVerdict


class ClaimCorrectionOutput(BaseModel):
    correction: ClaimCorrection
    raw_response: LLMResponse | None = None


class ClaimCorrectionAgent(Agent[ClaimCorrectionInput, ClaimCorrectionOutput]):
    name = "claim_correction_agent"

    def __init__(self, llm_provider: LLMProvider | None = None) -> None:
        self.llm_provider = llm_provider or MockLLMProvider()

    def run(self, input_data: ClaimCorrectionInput) -> ClaimCorrectionOutput:
        verdict_label = getattr(input_data.verdict.verdict, "value", str(input_data.verdict.verdict))

        if verdict_label not in {"contradicted", "partial", "partially_supported", "contested"}:
            return ClaimCorrectionOutput(
                correction=ClaimCorrection(
                    claim_id=input_data.claim.claim_id,
                    needs_correction=False,
                    rationale=(
                        "No correction proposed because the claim is not classified "
                        "as contradicted, partial, or contested."
                    ),
                )
            )

        deterministic_correction = self._score_correction(input_data)
        if deterministic_correction is not None:
            return ClaimCorrectionOutput(correction=deterministic_correction)

        request = self._build_request(input_data)
        response = self.llm_provider.generate(request)
        payload = self._safe_json_loads(response.content)

        if payload is None:
            return ClaimCorrectionOutput(
                correction=ClaimCorrection(
                    claim_id=input_data.claim.claim_id,
                    needs_correction=False,
                    rationale="No correction proposed because the LLM response was not valid JSON.",
                ),
                raw_response=response,
            )

        correction = self._parse_correction(input_data, payload)
        if not correction.needs_correction:
            deterministic_correction = self._score_correction(input_data)
            if deterministic_correction is not None:
                return ClaimCorrectionOutput(
                    correction=deterministic_correction,
                    raw_response=response,
                )

        return ClaimCorrectionOutput(correction=correction, raw_response=response)

    def _build_request(self, input_data: ClaimCorrectionInput) -> LLMRequest:
        evidence_payload = [
            {
                "evidence_id": evidence.evidence_id,
                "title": evidence.title,
                "source_url": evidence.url,
                "evidence_text": evidence.evidence_text[:1200],
            }
            for evidence in input_data.evidence[:8]
        ]
        stance_payload = [stance.model_dump(mode="json") for stance in input_data.stances[:12]]

        return LLMRequest(
            messages=[
                LLMMessage(
                    role="system",
                    content=(
                        "You are a claim correction agent for a verification system. "
                        "Use only the supplied claim, verdict, evidence, and stance results. "
                        "Do not use domain-specific memorized facts or hidden rules. "
                        "Return valid JSON only."
                    ),
                ),
                LLMMessage(
                    role="user",
                    content=(
                        "Decide whether the claim needs a corrected version. "
                        "Only propose a correction when it is directly supported by the supplied evidence.\n\n"
                        "Return exactly this JSON object shape:\n"
                        "{\n"
                        '  "needs_correction": true,\n'
                        '  "corrected_claim": "evidence-backed corrected claim or null",\n'
                        '  "correction_type": "entity_replacement|date_correction|numeric_correction|scope_correction|none",\n'
                        '  "changed_fields": [{"field": "subject", "original": "...", "corrected": "..."}],\n'
                        '  "confidence": 0.82,\n'
                        '  "evidence_ids": ["evidence id"],\n'
                        '  "rationale": "brief explanation grounded in evidence"\n'
                        "}\n\n"
                        f"CLAIM:\n{input_data.claim.model_dump(mode='json')}\n\n"
                        f"VERDICT:\n{input_data.verdict.model_dump(mode='json')}\n\n"
                        f"EVIDENCE:\n{json.dumps(evidence_payload, ensure_ascii=False)}\n\n"
                        f"STANCES:\n{json.dumps(stance_payload, ensure_ascii=False)}"
                    ),
                ),
            ],
            temperature=0.0,
            response_format="json",
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

    def _parse_correction(
        self,
        input_data: ClaimCorrectionInput,
        payload: dict,
    ) -> ClaimCorrection:
        needs_correction = bool(payload.get("needs_correction"))
        corrected_claim = payload.get("corrected_claim")
        corrected_claim = str(corrected_claim).strip() if corrected_claim else None

        if needs_correction and not corrected_claim:
            needs_correction = False

        changed_fields = []
        raw_fields = payload.get("changed_fields")
        if isinstance(raw_fields, list):
            for item in raw_fields:
                if not isinstance(item, dict):
                    continue
                changed_fields.append(
                    ClaimCorrectionChange(
                        field=str(item.get("field") or "unspecified"),
                        original=(
                            str(item.get("original"))
                            if item.get("original") is not None
                            else None
                        ),
                        corrected=(
                            str(item.get("corrected"))
                            if item.get("corrected") is not None
                            else None
                        ),
                    )
                )

        evidence_ids = payload.get("evidence_ids")
        if not isinstance(evidence_ids, list):
            evidence_ids = []

        return ClaimCorrection(
            claim_id=input_data.claim.claim_id,
            needs_correction=needs_correction,
            corrected_claim=corrected_claim if needs_correction else None,
            correction_type=str(payload.get("correction_type") or "none"),
            changed_fields=changed_fields if needs_correction else [],
            confidence=self._parse_confidence(payload.get("confidence")),
            evidence_ids=[str(item) for item in evidence_ids],
            rationale=str(payload.get("rationale") or "").strip(),
        )

    def _parse_confidence(self, value: object) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.0

        return max(0.0, min(1.0, confidence))

    def _score_correction(self, input_data: ClaimCorrectionInput) -> ClaimCorrection | None:
        score_correction = build_score_correction(
            claim_text=input_data.claim.claim_text,
            evidence_texts=[
                f"{evidence.title or ''}\n{evidence.evidence_text}"
                for evidence in input_data.evidence
            ],
        )
        if score_correction is None:
            return None

        corrected_claim, original_score, corrected_score = score_correction
        evidence_ids = [
            stance.evidence_id
            for stance in input_data.stances
            if getattr(stance.stance, "value", str(stance.stance)) == "contradicts"
        ]

        return ClaimCorrection(
            claim_id=input_data.claim.claim_id,
            needs_correction=True,
            corrected_claim=corrected_claim,
            correction_type="numeric_correction",
            changed_fields=[
                ClaimCorrectionChange(
                    field="score",
                    original=original_score,
                    corrected=corrected_score,
                )
            ],
            confidence=0.9,
            evidence_ids=evidence_ids,
            rationale="Evidence for the same matchup reports a different score.",
        )
