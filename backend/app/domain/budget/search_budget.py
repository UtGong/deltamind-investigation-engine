from pydantic import BaseModel

from app.core.config import get_settings
from app.schemas.search import SearchPlan, SearchQuery


class SearchBudgetDecision(BaseModel):
    allowed_queries: list[SearchQuery]
    blocked_queries: list[SearchQuery]
    reason: str


class SearchBudgetController:
    def decide(self, search_plan: SearchPlan) -> SearchBudgetDecision:
        settings = get_settings()

        if not search_plan.should_use_paid_search:
            free_queries = [
                query for query in search_plan.queries
                if query.cost_tier != "paid"
            ]
            blocked_queries = [
                query for query in search_plan.queries
                if query.cost_tier == "paid"
            ]

            return SearchBudgetDecision(
                allowed_queries=free_queries,
                blocked_queries=blocked_queries,
                reason="Planner did not require paid search.",
            )

        if not settings.allow_paid_search:
            return SearchBudgetDecision(
                allowed_queries=[
                    query for query in search_plan.queries
                    if query.cost_tier != "paid"
                ],
                blocked_queries=[
                    query for query in search_plan.queries
                    if query.cost_tier == "paid"
                ],
                reason="Paid search is disabled by configuration.",
            )

        allowed_paid_count = min(
            search_plan.max_paid_search_calls,
            settings.max_paid_search_calls_per_case,
        )

        allowed_queries: list[SearchQuery] = []
        blocked_queries: list[SearchQuery] = []
        used_paid_count = 0

        for query in search_plan.queries:
            if query.cost_tier != "paid":
                allowed_queries.append(query)
                continue

            if used_paid_count < allowed_paid_count:
                allowed_queries.append(query)
                used_paid_count += 1
            else:
                blocked_queries.append(query)

        return SearchBudgetDecision(
            allowed_queries=allowed_queries,
            blocked_queries=blocked_queries,
            reason=(
                f"Allowed {used_paid_count} paid search call(s). "
                f"Blocked {len(blocked_queries)} paid search call(s)."
            ),
        )
