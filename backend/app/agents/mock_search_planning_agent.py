from pydantic import BaseModel

from app.agents.base import Agent
from app.core.constants import ClaimType
from app.schemas.agent import AtomicClaim
from app.schemas.search import SearchPlan, SearchQuery


class MockSearchPlanningInput(BaseModel):
    claim: AtomicClaim


class MockSearchPlanningAgent(Agent[MockSearchPlanningInput, SearchPlan]):
    name = "mock_search_planning_agent"

    def run(self, input_data: MockSearchPlanningInput) -> SearchPlan:
        claim = input_data.claim
        query_text = claim.claim_text.strip()

        queries = [
            SearchQuery(
                query_id=f"{claim.claim_id}_query_1",
                claim_id=claim.claim_id,
                query=f"{query_text} official source",
                purpose="Find official or primary confirmation.",
                provider="mock",
            ),
            SearchQuery(
                query_id=f"{claim.claim_id}_query_2",
                claim_id=claim.claim_id,
                query=f"{query_text} independent report",
                purpose="Find independent corroborating or conflicting reports.",
                provider="mock",
            ),
        ]

        if claim.claim_type == ClaimType.TRANSFER:
            queries.append(
                SearchQuery(
                    query_id=f"{claim.claim_id}_query_3",
                    claim_id=claim.claim_id,
                    query=f"{query_text} roster registration transfer",
                    purpose="Check roster or registration evidence.",
                    provider="mock",
                )
            )

        if claim.claim_type == ClaimType.INJURY:
            queries.append(
                SearchQuery(
                    query_id=f"{claim.claim_id}_query_3",
                    claim_id=claim.claim_id,
                    query=f"{query_text} team injury report availability",
                    purpose="Check injury or availability reports.",
                    provider="mock",
                )
            )

        if claim.claim_type == ClaimType.RESULT:
            queries.append(
                SearchQuery(
                    query_id=f"{claim.claim_id}_query_3",
                    claim_id=claim.claim_id,
                    query=f"{query_text} official match result",
                    purpose="Check official result database.",
                    provider="mock",
                )
            )

        return SearchPlan(
            claim_id=claim.claim_id,
            queries=queries,
        )
