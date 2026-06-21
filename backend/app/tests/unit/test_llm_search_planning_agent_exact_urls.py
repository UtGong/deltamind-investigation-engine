from app.agents.llm_search_planning_agent import (
    LLMSearchPlanningAgent,
    LLMSearchPlanningInput,
)
from app.core.constants import ClaimType, SourceType
from app.providers.llm.base import LLMProvider
from app.schemas.agent import AtomicClaim
from app.schemas.llm import LLMRequest, LLMResponse


class FakePlannerLLMProvider(LLMProvider):
    name = "fake_planner_llm"

    def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content="""
            {
              "source_candidates": [
                {
                  "name": "NBA official article",
                  "domain": "nba.com",
                  "url": "https://www.nba.com/news/boston-celtics-win-2024-nba-finals",
                  "expected_source_type": "official",
                  "rationale": "Official league article for the Finals result.",
                  "priority": 1
                }
              ],
              "queries": [
                {
                  "query": "Boston Celtics won 2024 NBA Finals official NBA",
                  "purpose": "Find official confirmation.",
                  "cost_tier": "free",
                  "expected_source_type": "official",
                  "target_domains": ["nba.com"],
                  "provider": "configured_free_provider"
                }
              ],
              "should_use_paid_search": false,
              "paid_search_rationale": "Direct/free sources should be enough.",
              "max_paid_search_calls": 0
            }
            """,
            provider=self.name,
            model="fake-model",
            input_tokens=10,
            output_tokens=10,
            estimated_cost_usd=0.0,
        )


def test_llm_search_planning_agent_preserves_exact_candidate_url():
    agent = LLMSearchPlanningAgent(llm_provider=FakePlannerLLMProvider())

    output = agent.run(
        LLMSearchPlanningInput(
            claim=AtomicClaim(
                claim_id="claim_1",
                claim_text="The Boston Celtics won the 2024 NBA Finals.",
                claim_type=ClaimType.RESULT,
                confidence=0.95,
            )
        )
    )

    plan = output.search_plan

    assert len(plan.source_candidates) == 1
    assert plan.source_candidates[0].url == "https://www.nba.com/news/boston-celtics-win-2024-nba-finals"
    assert plan.source_candidates[0].expected_source_type == SourceType.OFFICIAL

    assert len(plan.queries) == 1
    assert plan.queries[0].provider == "configured_free_provider"
    assert plan.queries[0].target_domains == ["nba.com"]
