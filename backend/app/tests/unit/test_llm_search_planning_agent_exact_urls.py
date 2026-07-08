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
                  "name": "official article",
                  "domain": "nba.com",
                  "url": "https://www.nba.com/news/boston-celtics-win-2024-example-final",
                  "expected_source_type": "official",
                  "rationale": "Official league article for the Finals result.",
                  "priority": 1
                }
              ],
              "queries": [
                {
                  "query": "Team Green won 2024 Example Final official Example League",
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


class EmptyPlannerLLMProvider(LLMProvider):
    name = "empty_planner_llm"

    def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content='{"source_candidates": [], "queries": []}',
            provider=self.name,
            model="fake-model",
            input_tokens=10,
            output_tokens=3,
            estimated_cost_usd=0.0,
        )


class BadFragmentPlannerLLMProvider(LLMProvider):
    name = "bad_fragment_planner_llm"

    def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content="""
            {
              "source_candidates": [
                {
                  "name": "Official source",
                  "domain": "example.com",
                  "url": null,
                  "expected_source_type": "official",
                  "rationale": "Official source, but exact article URL is not known.",
                  "priority": 1
                }
              ],
              "queries": [
                {
                  "query": "with a 3-1 win",
                  "purpose": "numeric claim verification",
                  "cost_tier": "free",
                  "expected_source_type": "official",
                  "target_domains": ["example.com"],
                  "provider": "configured_free_provider"
                }
              ],
              "should_use_paid_search": false,
              "paid_search_rationale": null,
              "max_paid_search_calls": 0
            }
            """,
            provider=self.name,
            model="fake-model",
            input_tokens=10,
            output_tokens=10,
            estimated_cost_usd=0.0,
        )


class CopiedNbaPlannerLLMProvider(LLMProvider):
    name = "copied_nba_planner_llm"

    def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content="""
            {
              "source_candidates": [
                {
                  "name": "nba.com",
                  "domain": "nba.com",
                  "url": "https://www.nba.com/news/source-article",
                  "expected_source_type": "official",
                  "rationale": "Official source likely containing the relevant evidence.",
                  "priority": 1,
                  "validation_terms": ["score 3-1"]
                }
              ],
              "queries": [
                {
                  "query": "NBA match result with a 3-1 win",
                  "purpose": "evidence retrieval",
                  "cost_tier": "free",
                  "expected_source_type": "official",
                  "target_domains": ["nba.com"],
                  "provider": "configured_free_provider",
                  "validation_terms": ["score 3-1"]
                }
              ],
              "should_use_paid_search": false,
              "paid_search_rationale": null,
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
                claim_text="The Team Green won the 2024 Example Final.",
                claim_type=ClaimType.RESULT,
                confidence=0.95,
            )
        )
    )

    plan = output.search_plan

    exact_candidate = next(
        candidate
        for candidate in plan.source_candidates
        if candidate.url == "https://www.nba.com/news/boston-celtics-win-2024-example-final"
    )
    assert exact_candidate.expected_source_type == SourceType.OFFICIAL

    assert plan.queries[0].provider == "configured_free_provider"
    assert plan.queries[0].target_domains == ["nba.com"]


def test_llm_search_planning_agent_falls_back_when_plan_is_empty():
    agent = LLMSearchPlanningAgent(llm_provider=EmptyPlannerLLMProvider())

    output = agent.run(
        LLMSearchPlanningInput(
            claim=AtomicClaim(
                claim_id="claim_score",
                claim_text="Belgium beats USA with a 3-1 win in the Round of 16",
                claim_type=ClaimType.RESULT,
                confidence=0.95,
            )
        )
    )

    plan = output.search_plan

    domains = {candidate.domain for candidate in plan.source_candidates}
    assert "fifa.com" in domains
    assert "espn.com" in domains
    assert "example.com" not in domains

    query_texts = [query.query for query in plan.queries]
    assert any(
        query == "Belgium vs USA 2026 FIFA World Cup score 3-1"
        for query in query_texts
    )
    assert any(query.validation_terms for query in plan.queries)
    assert plan.queries[0].provider == "configured_free_provider"


def test_llm_search_planning_agent_repairs_placeholder_and_fragment_plan():
    agent = LLMSearchPlanningAgent(llm_provider=BadFragmentPlannerLLMProvider())

    output = agent.run(
        LLMSearchPlanningInput(
            claim=AtomicClaim(
                claim_id="claim_score",
                claim_text="Belgium beats USA with a 3-1 win in the Round of 16",
                claim_type=ClaimType.RESULT,
                confidence=0.95,
            )
        )
    )

    plan = output.search_plan

    assert all(candidate.domain != "example.com" for candidate in plan.source_candidates)
    assert {candidate.domain for candidate in plan.source_candidates} >= {"fifa.com", "espn.com"}
    assert all(candidate.validation_terms for candidate in plan.source_candidates)
    assert all(candidate.source_confidence >= 0.0 for candidate in plan.source_candidates)

    assert all(query.query != "with a 3-1 win" for query in plan.queries)
    assert all(
        "belgium" in query.query.lower() or "usa" in query.query.lower()
        for query in plan.queries
    )
    assert any("score 3-1" in query.query.lower() for query in plan.queries)


def test_llm_search_planning_agent_rejects_copied_nba_plan_for_world_cup_claim():
    agent = LLMSearchPlanningAgent(llm_provider=CopiedNbaPlannerLLMProvider())

    output = agent.run(
        LLMSearchPlanningInput(
            claim=AtomicClaim(
                claim_id="claim_worldcup_score",
                claim_text=(
                    "Belgium beats USA with a 3-1 win in the Round of 16 "
                    "in WorldCup 2026 v"
                ),
                claim_type=ClaimType.RESULT,
                confidence=0.95,
            )
        )
    )

    plan = output.search_plan

    assert all(candidate.domain != "nba.com" for candidate in plan.source_candidates)
    assert {candidate.domain for candidate in plan.source_candidates} >= {"fifa.com", "espn.com"}
    assert all("nba" not in query.query.lower() for query in plan.queries)
    assert any(
        query.query == "Belgium vs USA 2026 FIFA World Cup score 3-1"
        for query in plan.queries
    )
    assert any("round of 16" in query.query.lower() for query in plan.queries)
