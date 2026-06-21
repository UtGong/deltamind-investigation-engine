import re

from pydantic import BaseModel

from app.agents.base import Agent
from app.schemas.agent import AtomicClaim, EvidenceItem
from app.schemas.search import SearchResult


class SearchEvidenceInput(BaseModel):
    claim: AtomicClaim
    search_results: list[SearchResult]


class SearchEvidenceAgent(Agent[SearchEvidenceInput, list[EvidenceItem]]):
    name = "search_evidence_agent"

    def run(self, input_data: SearchEvidenceInput) -> list[EvidenceItem]:
        evidence_items: list[EvidenceItem] = []

        for index, result in enumerate(input_data.search_results, start=1):
            source_id = self._make_source_id(result.domain or result.source_name or "unknown")

            evidence_items.append(
                EvidenceItem(
                    evidence_id=f"{input_data.claim.claim_id}_evidence_{index}",
                    claim_id=input_data.claim.claim_id,
                    source_id=source_id,
                    url=result.url,
                    title=result.title,
                    published_at=result.published_at,
                    retrieved_at=result.retrieved_at,
                    evidence_text=result.snippet,
                    independence_group=result.domain or result.source_name or result.result_id,
                    reliability=result.reliability,
                    independence=result.independence,
                    freshness=result.freshness,
                    specificity=result.specificity,
                )
            )

        return evidence_items

    def _make_source_id(self, value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).strip("_")
        return f"source_{normalized or 'unknown'}"
