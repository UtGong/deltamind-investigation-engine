from app.agents.direct_source_fetch_agent import (
    DirectSourceFetchAgent,
    DirectSourceFetchInput,
)
from app.agents.url_fetch_agent import UrlFetchOutput
from app.core.constants import ClaimType, SourceType
from app.schemas.agent import AtomicClaim
from app.schemas.search import SearchPlan, SourceCandidate


class FakeUrlFetchAgent:
    def run(self, input_data):
        return UrlFetchOutput(
            url=str(input_data.url),
            final_url=str(input_data.url),
            status_code=200,
            title="Official source",
            text="Team A won the final 3-1.",
            error=None,
        )


def test_direct_source_fetch_agent_fetches_planner_candidate_url():
    agent = DirectSourceFetchAgent(url_fetch_agent=FakeUrlFetchAgent())

    claim = AtomicClaim(
        claim_id="claim_1",
        claim_text="Team A won the final 3-1.",
        claim_type=ClaimType.RESULT,
        confidence=0.9,
    )

    search_plan = SearchPlan(
        claim_id="claim_1",
        source_candidates=[
            SourceCandidate(
                name="Official source",
                domain="example.com",
                url="https://example.com/source",
                expected_source_type=SourceType.OFFICIAL,
                rationale="Planner selected this as a direct official source.",
                priority=1,
            )
        ],
        queries=[],
        should_use_paid_search=False,
        paid_search_rationale="No paid search needed.",
        max_paid_search_calls=0,
    )

    output = agent.run(
        DirectSourceFetchInput(
            claim=claim,
            search_plan=search_plan,
        )
    )

    assert len(output.results) == 1
    assert output.results[0].url == "https://example.com/source"
    assert output.results[0].domain == "example.com"
    assert output.results[0].source_type == SourceType.UNKNOWN
    assert "Team A won the final 3-1." in output.results[0].snippet


def test_direct_source_fetch_agent_skips_candidate_without_url():
    agent = DirectSourceFetchAgent(url_fetch_agent=FakeUrlFetchAgent())

    claim = AtomicClaim(
        claim_id="claim_1",
        claim_text="Team A won the final 3-1.",
        claim_type=ClaimType.RESULT,
        confidence=0.9,
    )

    search_plan = SearchPlan(
        claim_id="claim_1",
        source_candidates=[
            SourceCandidate(
                name="Official source",
                domain="example.com",
                url=None,
                expected_source_type=SourceType.OFFICIAL,
                rationale="Planner selected this source but did not provide exact URL.",
                priority=1,
            )
        ],
        queries=[],
        should_use_paid_search=False,
        paid_search_rationale="No paid search needed.",
        max_paid_search_calls=0,
    )

    output = agent.run(
        DirectSourceFetchInput(
            claim=claim,
            search_plan=search_plan,
        )
    )

    assert output.results == []
    assert output.skipped_candidates == ["example.com"]
