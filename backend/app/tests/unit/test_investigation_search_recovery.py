from types import SimpleNamespace

from app.core.constants import ClaimType, StanceLabel
from app.domain.investigations import service as service_module
from app.domain.investigations.service import InvestigationService
from app.schemas.agent import AtomicClaim, EvidenceItem, StanceResult
from app.schemas.search import SearchPlan, SearchQuery, SearchResult


class RecordingAudit:
    def __init__(self) -> None:
        self.agent_runs = []
        self.costs = []

    def record_agent_run(self, **kwargs) -> None:
        self.agent_runs.append(kwargs)

    def record_cost(self, **kwargs) -> None:
        self.costs.append(kwargs)


class FakePaidSearchProvider:
    name = "fake_paid_search_provider"

    def __init__(self) -> None:
        self.queries = []

    def search(self, query: SearchQuery) -> list[SearchResult]:
        self.queries.append(query)
        return [
            SearchResult(
                result_id=f"{query.query_id}_result_1",
                query_id=query.query_id,
                title="Official match report",
                url="https://www.fifa.com/example-match-report",
                snippet="Belgium defeated USA 4-1 in the Round of 16.",
                domain="fifa.com",
            )
        ]


def test_paid_search_recovery_runs_when_free_search_returns_no_results(monkeypatch):
    monkeypatch.setattr(
        service_module,
        "get_settings",
        lambda: SimpleNamespace(
            allow_paid_search=True,
            max_paid_search_calls_per_case=1,
        ),
    )

    service = InvestigationService.__new__(InvestigationService)
    service.audit = RecordingAudit()
    service._paid_search_provider = FakePaidSearchProvider()

    claim = AtomicClaim(
        claim_id="claim_score",
        claim_text="Belgium won the match with a score of 3-1",
        claim_type=ClaimType.RESULT,
        confidence=0.95,
    )
    free_query = SearchQuery(
        query_id="claim_score_query_1",
        claim_id=claim.claim_id,
        query="Belgium vs USA 2026 FIFA World Cup score 3-1",
        purpose="Validate score.",
        cost_tier="free",
        provider="configured_free_provider",
        target_domains=["fifa.com"],
    )
    search_plan = SearchPlan(
        claim_id=claim.claim_id,
        queries=[free_query],
    )

    results = service._run_paid_search_recovery(
        case=SimpleNamespace(case_id="case_1"),
        claim=claim,
        search_plan=search_plan,
        allowed_queries=[free_query],
    )

    assert len(results) == 1
    assert service._paid_search_provider.queries[0].cost_tier == "paid"
    assert service._paid_search_provider.queries[0].provider == "configured_paid_provider"
    assert service._paid_search_provider.queries[0].target_domains == ["fifa.com"]
    assert any(
        run["metadata"]["stage"] == "paid_search_recovery"
        for run in service.audit.agent_runs
    )


def test_direct_source_fetch_skips_domain_expansion_when_search_results_exist():
    service = InvestigationService.__new__(InvestigationService)

    search_plan = SearchPlan(
        claim_id="claim_score",
        queries=[],
    )
    search_results = [
        SearchResult(
            result_id="result_1",
            query_id="query_1",
            title="USA 1-4 Belgium",
            url="https://www.fifa.com/example",
            snippet="USA 1-4 Belgium",
            domain="fifa.com",
        )
    ]

    assert service._should_run_direct_source_fetch(search_results, search_plan) is False


def test_direct_source_fetch_still_runs_for_exact_candidate_urls():
    service = InvestigationService.__new__(InvestigationService)

    search_plan = SearchPlan(
        claim_id="claim_score",
        source_candidates=[
            {
                "domain": "fifa.com",
                "url": "https://www.fifa.com/example",
                "rationale": "Exact official source URL.",
            }
        ],
        queries=[],
    )
    search_results = [
        SearchResult(
            result_id="result_1",
            query_id="query_1",
            title="USA 1-4 Belgium",
            url="https://www.fifa.com/example",
            snippet="USA 1-4 Belgium",
            domain="fifa.com",
        )
    ]

    assert service._should_run_direct_source_fetch(search_results, search_plan) is True


def test_free_search_stops_early_when_paid_recovery_is_available(monkeypatch):
    monkeypatch.setattr(
        service_module,
        "get_settings",
        lambda: SimpleNamespace(
            allow_paid_search=True,
            max_paid_search_calls_per_case=1,
        ),
    )

    service = InvestigationService.__new__(InvestigationService)
    query = SearchQuery(
        query_id="query_1",
        claim_id="claim_1",
        query="Belgium vs USA 2026 FIFA World Cup score",
        purpose="Find score.",
        cost_tier="free",
    )

    assert (
        service._should_stop_free_search_for_paid_recovery(
            query=query,
            search_results=[],
            empty_free_search_count=1,
            attempted_free_search_count=1,
        )
        is True
    )


def test_score_evidence_is_prioritized_and_stops_stance_classification():
    service = InvestigationService.__new__(InvestigationService)
    claim = AtomicClaim(
        claim_id="claim_score",
        claim_text="Belgium beats USA with a 3-1 win in the Round of 16",
        claim_type=ClaimType.RESULT,
        confidence=0.95,
    )
    weak_evidence = EvidenceItem(
        evidence_id="evidence_weak",
        claim_id=claim.claim_id,
        source_id="source_example",
        title="General preview",
        url="https://www.example.org/preview",
        evidence_text="The teams met in the tournament.",
    )
    score_evidence = EvidenceItem(
        evidence_id="evidence_score",
        claim_id=claim.claim_id,
        source_id="source_fifa",
        title="USA 1-4 Belgium | Result, Stats & Highlights",
        url="https://www.fifa.com/example",
        evidence_text="USA 1-4 Belgium in the Round of 16.",
    )
    evidence_items = [weak_evidence, score_evidence]

    prioritized = service._prioritize_evidence_for_stance(
        claim=claim,
        evidence_items=evidence_items,
    )
    stance = StanceResult(
        claim_id=claim.claim_id,
        evidence_id="evidence_score",
        stance=StanceLabel.CONTRADICTS,
        confidence=0.9,
        reason="Score differs.",
    )

    assert prioritized[0].title == "USA 1-4 Belgium | Result, Stats & Highlights"
    assert service._has_decisive_score_stance(claim=claim, stance=stance) is True
