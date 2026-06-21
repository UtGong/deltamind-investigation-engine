from pydantic import BaseModel

from app.agents.base import Agent
from app.core.config import get_settings
from app.core.constants import SourceType
from app.schemas.agent import AtomicClaim
from app.schemas.llm import LLMResponse
from app.schemas.search import SearchPlan, SearchQuery


class CostAwareSearchPlanningInput(BaseModel):
    claim: AtomicClaim


class CostAwareSearchPlanningOutput(BaseModel):
    search_plan: SearchPlan
    raw_response: LLMResponse


class CostAwareSearchPlanningAgent(
    Agent[CostAwareSearchPlanningInput, CostAwareSearchPlanningOutput]
):
    name = "cost_aware_search_planning_agent"

    def run(
        self,
        input_data: CostAwareSearchPlanningInput,
    ) -> CostAwareSearchPlanningOutput:
        settings = get_settings()
        claim = input_data.claim

        queries: list[SearchQuery] = []

        if settings.free_search_provider != "no_search":
            queries.extend(
                [
                    SearchQuery(
                        query_id=f"{claim.claim_id}_query_1",
                        claim_id=claim.claim_id,
                        query=f"{claim.claim_text} primary source",
                        purpose="Find a zero-cost primary or direct source if available.",
                        cost_tier="free",
                        expected_source_type=SourceType.UNKNOWN,
                        provider=settings.free_search_provider,
                    ),
                    SearchQuery(
                        query_id=f"{claim.claim_id}_query_2",
                        claim_id=claim.claim_id,
                        query=f"{claim.claim_text} independent report",
                        purpose="Find zero-cost independent corroboration if available.",
                        cost_tier="free",
                        expected_source_type=SourceType.UNKNOWN,
                        provider=settings.free_search_provider,
                    ),
                ]
            )

        should_use_paid_search = (
            settings.allow_paid_search
            and settings.max_paid_search_calls_per_case > 0
        )

        if should_use_paid_search:
            queries.append(
                SearchQuery(
                    query_id=f"{claim.claim_id}_paid_query_1",
                    claim_id=claim.claim_id,
                    query=claim.claim_text,
                    purpose="Paid fallback search because external verification is allowed by budget.",
                    cost_tier="paid",
                    expected_source_type=SourceType.UNKNOWN,
                    provider=settings.paid_search_provider,
                )
            )

        search_plan = SearchPlan(
            claim_id=claim.claim_id,
            source_candidates=[],
            queries=queries,
            should_use_paid_search=should_use_paid_search,
            paid_search_rationale=(
                "Paid search is allowed by configuration."
                if should_use_paid_search
                else "Paid search is disabled by configuration."
            ),
            max_paid_search_calls=1 if should_use_paid_search else 0,
        )

        raw_response = LLMResponse(
            content=search_plan.model_dump_json(),
            provider="internal_deterministic",
            model="cost-aware-search-planner-v0",
            input_tokens=0,
            output_tokens=0,
            estimated_cost_usd=0.0,
            metadata={"llm_used": False},
        )

        return CostAwareSearchPlanningOutput(
            search_plan=search_plan,
            raw_response=raw_response,
        )
