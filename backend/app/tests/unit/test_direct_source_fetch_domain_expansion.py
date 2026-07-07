from types import SimpleNamespace

from app.agents.direct_source_fetch_agent import (
    DirectSourceFetchAgent,
    DirectSourceFetchInput,
)
from app.core.constants import ClaimType, SourceType
from app.schemas.agent import AtomicClaim
from app.schemas.search import SearchPlan, SearchQuery, SourceCandidate


class FakeUrlFetchAgent:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def run(self, input_data):
        url = str(input_data.url)
        self.urls.append(url)

        if "example.org/search" in url:
            return SimpleNamespace(
                error=None,
                text="The Team Green won the 2024 Example Final.",
                final_url=url,
                title="Example League search result",
            )

        return SimpleNamespace(
            error="not needed",
            text=None,
            final_url=url,
            title=None,
        )


def test_direct_source_fetch_expands_domain_only_candidates():
    fake_fetcher = FakeUrlFetchAgent()

    agent = DirectSourceFetchAgent(
        url_fetch_agent=fake_fetcher,
        max_expanded_urls_per_candidate=3,
    )

    claim = AtomicClaim(
        claim_id="claim_test",
        claim_text="The Team Green won the 2024 Example Final.",
        claim_type=ClaimType.EVENT,
    )

    search_plan = SearchPlan(
        claim_id=claim.claim_id,
        source_candidates=[
            SourceCandidate(
                name="official website",
                domain="example.org",
                url=None,
                expected_source_type=SourceType.OFFICIAL,
                rationale="Official official source.",
                priority=1,
            )
        ],
        queries=[
            SearchQuery(
                query_id="query_1",
                claim_id=claim.claim_id,
                query="Team Green won 2024 Example Final",
                purpose="Find official confirmation.",
                cost_tier="free",
                expected_source_type=SourceType.OFFICIAL,
                target_domains=["example.org"],
                provider="configured_free_provider",
            )
        ],
    )

    output = agent.run(
        DirectSourceFetchInput(
            claim=claim,
            search_plan=search_plan,
        )
    )

    assert output.expanded_urls
    assert any("example.org/search" in url for url in output.expanded_urls)
    assert len(output.results) >= 1
    assert output.results[0].domain == "example.org"
    assert "Team Green won the 2024 Example Final" in output.results[0].snippet


def test_direct_source_fetch_does_not_fabricate_evidence_for_failed_url():
    class FailedFetch:
        error = True
        text = ""
        final_url = None
        title = None

    class FailingUrlFetchAgent:
        def run(self, input_data):
            return FailedFetch()

    claim = AtomicClaim(
        claim_id="C1",
        claim_text="The Team Blue won the 2023 Example Final.",
        claim_type=ClaimType.EVENT,
        subject="The Team Blue",
        predicate="won",
        object="the 2023 Example Final",
        confidence=1.0,
    )

    search_plan = SearchPlan(
        claim_id="C1",
        source_candidates=[
            SourceCandidate(
                name="official results page",
                domain="example.org",
                url="https://www.example.org/results/example-final",
                expected_source_type=SourceType.OFFICIAL,
                rationale="Official source candidate.",
                priority=1,
            )
        ],
    )

    output = DirectSourceFetchAgent(url_fetch_agent=FailingUrlFetchAgent()).run(
        DirectSourceFetchInput(claim=claim, search_plan=search_plan)
    )

    assert output.results == []
    assert output.failed_urls == ["https://www.example.org/results/example-final"]
