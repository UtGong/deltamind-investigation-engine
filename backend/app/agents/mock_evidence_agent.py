from pydantic import BaseModel

from app.agents.base import Agent
from app.domain.cases.models import utc_now
from app.schemas.agent import AtomicClaim, EvidenceItem


class MockEvidenceInput(BaseModel):
    claim: AtomicClaim


class MockEvidenceAgent(Agent[MockEvidenceInput, list[EvidenceItem]]):
    name = "mock_evidence_agent"

    def run(self, input_data: MockEvidenceInput) -> list[EvidenceItem]:
        claim = input_data.claim

        return [
            EvidenceItem(
                evidence_id=f"{claim.claim_id}_evidence_1",
                claim_id=claim.claim_id,
                source_id="mock_official_source",
                url="https://example.com/mock-official-source",
                title="Mock Official Evidence",
                retrieved_at=utc_now(),
                evidence_text=f"Mock evidence generated for claim: {claim.claim_text}",
                independence_group="mock_official_group",
                reliability=0.90,
                independence=0.90,
                freshness=0.90,
                specificity=0.90,
            )
        ]
