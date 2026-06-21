from app.agents.planner_source_assessment_agent import (
    PlannerSourceAssessmentAgent,
    PlannerSourceAssessmentInput,
)
from app.core.constants import ClaimType, SourceType
from app.schemas.agent import AtomicClaim
from app.schemas.search import SearchPlan, SearchQuery, SearchResult, SourceCandidate


def test_planner_source_assessment_uses_planner_candidate_not_hardcoded_domain():
    agent = PlannerSourceAssessmentAgent()

    claim = AtomicClaim(
        claim_id="claim_1",
        claim_text="Team A won the final.",
        claim_type=ClaimType.RESULT,
        confidence=0.9,
    )

    search_plan = SearchPlan(
        claim_id="claim_1",
        source_candidates=[
            SourceCandidate(
                name="Planner Official Candidate",
                domain="example-official-source.com",
                expected_source_type=SourceType.OFFICIAL,
                rationale="The planner identified this as the direct competition source.",
                priority=1,
            )
        ],
        queries=[
            SearchQuery(
                query_id="query_1",
                claim_id="claim_1",
                query="Team A final result",
                purpose="Verify result.",
                expected_source_type=SourceType.UNKNOWN,
            )
        ],
    )

    search_results = [
        SearchResult(
            result_id="result_1",
            query_id="query_1",
            title="Final result",
            url="https://www.example-official-source.com/final",
            snippet="Team A won the final.",
            domain="example-official-source.com",
            source_type=SourceType.UNKNOWN,
            reliability=0.5,
        )
    ]

    output = agent.run(
        PlannerSourceAssessmentInput(
            claim=claim,
            search_plan=search_plan,
            search_results=search_results,
        )
    )

    assert len(output.assessed_results) == 1
    assert output.assessed_results[0].source_type == SourceType.OFFICIAL
    assert output.assessed_results[0].reliability > 0.5
    assert "planner-proposed source candidate" in output.notes[0].rationale


def test_planner_source_assessment_keeps_unknown_when_no_planner_match():
    agent = PlannerSourceAssessmentAgent()

    claim = AtomicClaim(
        claim_id="claim_1",
        claim_text="Team A won the final.",
        claim_type=ClaimType.RESULT,
        confidence=0.9,
    )

    search_plan = SearchPlan(
        claim_id="claim_1",
        source_candidates=[],
        queries=[
            SearchQuery(
                query_id="query_1",
                claim_id="claim_1",
                query="Team A final result",
                purpose="Verify result.",
                expected_source_type=SourceType.UNKNOWN,
            )
        ],
    )

    search_results = [
        SearchResult(
            result_id="result_1",
            query_id="query_1",
            title="Final result",
            url="https://random-site.example/final",
            snippet="Team A won the final.",
            domain="random-site.example",
            source_type=SourceType.UNKNOWN,
            reliability=0.5,
        )
    ]

    output = agent.run(
        PlannerSourceAssessmentInput(
            claim=claim,
            search_plan=search_plan,
            search_results=search_results,
        )
    )

    assert output.assessed_results[0].source_type == SourceType.UNKNOWN
    assert output.assessed_results[0].reliability == 0.45
