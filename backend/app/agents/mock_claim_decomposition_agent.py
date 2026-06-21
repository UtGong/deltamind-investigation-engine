import re

from pydantic import BaseModel

from app.agents.base import Agent
from app.core.constants import ClaimType
from app.schemas.agent import AtomicClaim


class MockClaimDecompositionInput(BaseModel):
    case_id: str
    input_text: str


class MockClaimDecompositionAgent(
    Agent[MockClaimDecompositionInput, list[AtomicClaim]]
):
    name = "mock_claim_decomposition_agent"

    def run(self, input_data: MockClaimDecompositionInput) -> list[AtomicClaim]:
        sentences = self._split_sentences(input_data.input_text)

        return [
            AtomicClaim(
                claim_id=f"{input_data.case_id}_claim_{index + 1}",
                claim_text=sentence,
                claim_type=self._infer_claim_type(sentence),
                confidence=0.75,
            )
            for index, sentence in enumerate(sentences)
        ]

    def _split_sentences(self, text: str) -> list[str]:
        candidates = re.split(r"(?<=[.!?])\s+|\n+", text.strip())
        sentences = [item.strip() for item in candidates if item.strip()]
        return sentences or [text.strip()]

    def _infer_claim_type(self, text: str) -> ClaimType:
        lowered = text.lower()

        if any(word in lowered for word in ["score", "won", "lost", "beat", "defeated"]):
            return ClaimType.RESULT

        if any(word in lowered for word in ["injury", "injured", "available", "returned"]):
            return ClaimType.INJURY

        if any(word in lowered for word in ["transfer", "joined", "signed"]):
            return ClaimType.TRANSFER

        if any(word in lowered for word in ["schedule", "fixture", "match date"]):
            return ClaimType.SCHEDULE

        return ClaimType.UNKNOWN
