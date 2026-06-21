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

        if "nba.com/search" in url:
            return SimpleNamespace(
                error=None,
                text="The Boston Celtics won the 2024 NBA Finals.",
                final_url=url,
                title="NBA search result",
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
        claim_text="The Boston Celtics won the 2024 NBA Finals.",
        claim_type=ClaimType.EVENT,
    )

    search_plan = SearchPlan(
        claim_id=claim.claim_id,
        source_candidates=[
            SourceCandidate(
                name="NBA official website",
                domain="nba.com",
                url=None,
                expected_source_type=SourceType.OFFICIAL,
                rationale="Official NBA source.",
                priority=1,
            )
        ],
        queries=[
            SearchQuery(
                query_id="query_1",
                claim_id=claim.claim_id,
                query="Boston Celtics won 2024 NBA Finals",
                purpose="Find official confirmation.",
                cost_tier="free",
                expected_source_type=SourceType.OFFICIAL,
                target_domains=["nba.com"],
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
    assert any("nba.com/search" in url for url in output.expanded_urls)
    assert len(output.results) >= 1
    assert output.results[0].domain == "nba.com"
    assert "Boston Celtics won the 2024 NBA Finals" in output.results[0].snippet


def test_direct_source_fetch_uses_dev_fixture_for_failed_2023_nba_finals_url(monkeypatch):
    from app.agents.direct_source_fetch_agent import DirectSourceFetchAgent, DirectSourceFetchInput
    from app.core.config import get_settings
    from app.core.constants import ClaimType, SourceType
    from app.schemas.agent import AtomicClaim
    from app.schemas.search import SearchPlan, SourceCandidate

    monkeypatch.setenv("DEV_LLM_FALLBACK_ENABLED", "true")
    if hasattr(get_settings, "cache_clear"):
        get_settings.cache_clear()

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
        claim_text="The Denver Nuggets won the 2023 NBA Finals.",
        claim_type=ClaimType.EVENT,
        subject="The Denver Nuggets",
        predicate="won",
        object="the 2023 NBA Finals",
        confidence=1.0,
    )

    search_plan = SearchPlan(
        claim_id="C1",
        source_candidates=[
            SourceCandidate(
                name="NBA official Finals page",
                domain="nba.com",
                url="https://www.nba.com/playoffs/2023/nba-finals",
                expected_source_type=SourceType.OFFICIAL,
                rationale="Official Finals page.",
                priority=1,
            )
        ],
    )

    output = DirectSourceFetchAgent(
        url_fetch_agent=FailingUrlFetchAgent()
    ).run(
        DirectSourceFetchInput(
            claim=claim,
            search_plan=search_plan,
        )
    )

    assert len(output.results) == 1
    assert output.results[0].url == "https://www.nba.com/playoffs/2023/nba-finals"
    assert "Denver Nuggets defeated the Miami Heat" in output.results[0].snippet
    assert output.results[0].source_type == SourceType.OFFICIAL

    monkeypatch.setenv("DEV_LLM_FALLBACK_ENABLED", "false")
    if hasattr(get_settings, "cache_clear"):
        get_settings.cache_clear()
