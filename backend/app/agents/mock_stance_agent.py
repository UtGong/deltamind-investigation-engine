from pydantic import BaseModel

from app.agents.base import Agent
from app.core.constants import StanceLabel
from app.schemas.agent import AtomicClaim, EvidenceItem, StanceResult


class MockStanceInput(BaseModel):
    claim: AtomicClaim
    evidence: EvidenceItem


class MockStanceAgent(Agent[MockStanceInput, StanceResult]):
    name = "mock_stance_agent"

    def run(self, input_data: MockStanceInput) -> StanceResult:
        claim_text = input_data.claim.claim_text.lower()

        if any(word in claim_text for word in ["rumor", "unconfirmed", "allegedly"]):
            return StanceResult(
                claim_id=input_data.claim.claim_id,
                evidence_id=input_data.evidence.evidence_id,
                stance=StanceLabel.INSUFFICIENT,
                confidence=0.75,
                reason="Mock stance: claim appears uncertain or unconfirmed.",
            )

        if any(word in claim_text for word in ["false", "denied", "not true"]):
            return StanceResult(
                claim_id=input_data.claim.claim_id,
                evidence_id=input_data.evidence.evidence_id,
                stance=StanceLabel.CONTRADICTS,
                confidence=0.90,
                reason="Mock stance: claim contains contradiction-oriented wording.",
            )

        return StanceResult(
            claim_id=input_data.claim.claim_id,
            evidence_id=input_data.evidence.evidence_id,
            stance=StanceLabel.SUPPORTS,
            confidence=0.90,
            reason="Mock stance: evidence is treated as supporting this claim.",
        )
