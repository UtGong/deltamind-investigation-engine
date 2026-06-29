from fastapi import HTTPException, status

from app.agents.cost_aware_search_planning_agent import (
    CostAwareSearchPlanningAgent,
    CostAwareSearchPlanningInput,
)
from app.agents.direct_source_fetch_agent import (
    DirectSourceFetchAgent,
    DirectSourceFetchInput,
)
from app.agents.llm_claim_decomposition_agent import (
    LLMClaimDecompositionAgent,
    LLMClaimDecompositionInput,
)
from app.agents.llm_search_planning_agent import (
    LLMSearchPlanningAgent,
    LLMSearchPlanningInput,
)
from app.agents.claim_correction_agent import (
    ClaimCorrectionAgent,
    ClaimCorrectionInput,
)
from app.agents.llm_stance_agent import LLMStanceAgent, LLMStanceInput
from app.agents.planner_source_assessment_agent import (
    PlannerSourceAssessmentAgent,
    PlannerSourceAssessmentInput,
)
from app.agents.search_result_page_fetch_agent import (
    SearchResultPageFetchAgent,
    SearchResultPageFetchInput,
)
from app.agents.provided_text_evidence_agent import (
    ProvidedTextEvidenceAgent,
    ProvidedTextEvidenceInput,
)
from app.agents.report_agent import ReportAgent, ReportAgentInput
from app.agents.search_evidence_agent import SearchEvidenceAgent, SearchEvidenceInput
from app.agents.url_fetch_agent import UrlFetchAgent, UrlFetchInput, UrlFetchOutput
from app.algorithm.pivot.scoring import score_claim
from app.domain.source_reliability.service import SourceReliabilityService
from app.algorithm.pivot.evidence_quality import filter_evidence_items
from app.core.config import get_settings
from app.core.constants import CaseStatus, CostType, InputType, VerdictLabel
from app.domain.audit.service import AuditService, audit_service
from app.domain.budget.search_budget import SearchBudgetController
from app.domain.cases.models import utc_now
from app.domain.cases.repository import CaseRepository, case_repository
from app.domain.investigations.repository import (
    InvestigationRepository,
    investigation_repository,
)
from app.domain.verified_claims.service import (
    VerifiedClaimService,
    verified_claim_service,
)
from app.providers.llm.factory import get_llm_provider
from app.providers.search.base import SearchProvider
from app.providers.search.factory import get_free_search_provider, get_paid_search_provider
from app.schemas.agent import EvidenceItem, PivotVerdict, StanceResult
from app.schemas.api import InvestigationResult
from app.schemas.correction import ClaimCorrection
from app.schemas.search import SearchQuery, SearchResult


class InvestigationService:
    def __init__(
        self,
        case_repo: CaseRepository,
        investigation_repo: InvestigationRepository,
        audit: AuditService,
        verified_claims: VerifiedClaimService,
    ) -> None:
        self.case_repo = case_repo
        self.investigation_repo = investigation_repo
        self.audit = audit
        self.verified_claims = verified_claims

        llm_provider = get_llm_provider()

        self.claim_agent = LLMClaimDecompositionAgent(llm_provider=llm_provider)

        if get_settings().search_planner_provider == "llm":
            self.search_planning_agent = LLMSearchPlanningAgent(llm_provider=llm_provider)
            self.search_planning_input_model = LLMSearchPlanningInput
        else:
            self.search_planning_agent = CostAwareSearchPlanningAgent()
            self.search_planning_input_model = CostAwareSearchPlanningInput

        self.search_budget_controller = SearchBudgetController()

        self.free_search_provider = get_free_search_provider()
        self._paid_search_provider: SearchProvider | None = None

        self.url_fetch_agent = UrlFetchAgent()
        self.direct_source_fetch_agent = DirectSourceFetchAgent(
            url_fetch_agent=self.url_fetch_agent
        )
        self.search_result_page_fetch_agent = SearchResultPageFetchAgent(
            url_fetch_agent=self.url_fetch_agent
        )
        self.provided_text_evidence_agent = ProvidedTextEvidenceAgent()
        self.source_assessment_agent = PlannerSourceAssessmentAgent()
        self.evidence_agent = SearchEvidenceAgent()
        self.stance_agent = LLMStanceAgent(llm_provider=llm_provider)
        self.report_agent = ReportAgent()

    def investigate_case(self, case_id: str) -> InvestigationResult:
        case = self.case_repo.get(case_id)

        if case is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Case not found: {case_id}",
            )

        running_case = case.model_copy(
            update={
                "status": CaseStatus.RUNNING,
                "updated_at": utc_now(),
            }
        )
        self.case_repo.update(running_case)

        investigation_input_text = case.input_text
        fetched_url: UrlFetchOutput | None = None

        if case.input_type == InputType.URL:
            fetched_url = self.url_fetch_agent.run(
                UrlFetchInput(url=case.input_text)
            )

            self.audit.record_agent_run(
                case_id=case.case_id,
                agent_name=self.url_fetch_agent.name,
                provider="direct_http_fetch",
                input_data={"url": case.input_text},
                output_data=fetched_url,
                metadata={
                    "stage": "url_fetch",
                    "status_code": fetched_url.status_code,
                    "has_text": bool(fetched_url.text),
                    "error": fetched_url.error,
                },
            )

            self.audit.record_cost(
                case_id=case.case_id,
                cost_type=CostType.SEARCH,
                provider="direct_http_fetch",
                units=0,
                unit_name="fetch_call",
                estimated_cost_usd=0.0,
                metadata={"agent_name": self.url_fetch_agent.name},
            )

            if fetched_url.text:
                investigation_input_text = fetched_url.text

        claim_agent_input = LLMClaimDecompositionInput(
            case_id=case.case_id,
            input_text=investigation_input_text,
        )
        try:
            claim_output = self.claim_agent.run(claim_agent_input)
        except Exception as error:
            self._fail_case_due_to_upstream_llm_error(
                case=running_case,
                stage="claim_decomposition",
                agent_name=self.claim_agent.name,
                error=error,
                input_data=claim_agent_input,
            )
        claims = claim_output.claims

        self.audit.record_agent_run(
            case_id=case.case_id,
            agent_name=self.claim_agent.name,
            provider=claim_output.raw_response.provider,
            model=claim_output.raw_response.model,
            input_data=claim_agent_input,
            output_data=claim_output,
            metadata={
                "stage": "claim_decomposition",
                "input_tokens": claim_output.raw_response.input_tokens,
                "output_tokens": claim_output.raw_response.output_tokens,
            },
        )
        self.audit.record_cost(
            case_id=case.case_id,
            cost_type=CostType.AGENT,
            provider=claim_output.raw_response.provider,
            units=claim_output.raw_response.input_tokens
            + claim_output.raw_response.output_tokens,
            unit_name="token",
            estimated_cost_usd=claim_output.raw_response.estimated_cost_usd,
            metadata={"agent_name": self.claim_agent.name},
        )

        evidence_items: list[EvidenceItem] = []
        stance_results: list[StanceResult] = []
        verdicts: list[PivotVerdict] = []
        corrections: list[ClaimCorrection] = []

        for claim in claims:
            cached_record = self.verified_claims.lookup(claim)

            self.audit.record_agent_run(
                case_id=case.case_id,
                agent_name="verified_claim_lookup",
                provider="internal_repository",
                input_data=claim,
                output_data=cached_record,
                metadata={
                    "stage": "verified_claim_lookup",
                    "claim_id": claim.claim_id,
                    "cache_hit": cached_record is not None,
                },
            )

            if cached_record is not None:
                cached_evidence, evidence_id_map = self._rehydrate_cached_evidence(
                    claim=claim,
                    cached_record=cached_record,
                )
                cached_stances = self._rehydrate_cached_stances(
                    claim=claim,
                    cached_record=cached_record,
                    evidence_id_map=evidence_id_map,
                )

                evidence_items.extend(cached_evidence)
                stance_results.extend(cached_stances)

                cached_verdict = PivotVerdict(
                    claim_id=claim.claim_id,
                    verdict=cached_record.verdict,
                    confidence=cached_record.confidence,
                    support_score=cached_record.support_score,
                    contradiction_score=cached_record.contradiction_score,
                    uncertainty_score=cached_record.uncertainty_score,
                    reason=f"Reused cached verification: {cached_record.reason}",
                    debug={
                        "cache_hit": True,
                        "normalized_claim_text": cached_record.normalized_claim_text,
                        "cached_updated_at": cached_record.updated_at.isoformat(),
                        "freshness_policy": cached_record.freshness_policy,
                        "expires_at": (
                            cached_record.expires_at.isoformat()
                            if cached_record.expires_at
                            else None
                        ),
                        "cached_evidence_count": len(cached_evidence),
                        "cached_stance_count": len(cached_stances),
                    },
                )
                verdicts.append(cached_verdict)

                self.audit.record_agent_run(
                    case_id=case.case_id,
                    agent_name="verified_claim_reuse",
                    provider="internal_repository",
                    input_data=claim,
                    output_data={
                        "verdict": cached_verdict,
                        "evidence_count": len(cached_evidence),
                        "stance_count": len(cached_stances),
                    },
                    metadata={
                        "stage": "verified_claim_reuse",
                        "claim_id": claim.claim_id,
                        "evidence_count": len(cached_evidence),
                        "stance_count": len(cached_stances),
                    },
                )

                continue

            search_plan_input = self.search_planning_input_model(claim=claim)
            try:
                search_plan_output = self.search_planning_agent.run(search_plan_input)
            except Exception as error:
                self._fail_case_due_to_upstream_llm_error(
                    case=running_case,
                    stage="search_planning",
                    agent_name=self.search_planning_agent.name,
                    error=error,
                    input_data=search_plan_input,
                    claim_id=claim.claim_id,
                )
            search_plan = search_plan_output.search_plan

            self.audit.record_agent_run(
                case_id=case.case_id,
                agent_name=self.search_planning_agent.name,
                provider=search_plan_output.raw_response.provider,
                model=search_plan_output.raw_response.model,
                input_data=search_plan_input,
                output_data=search_plan_output,
                metadata={
                    "stage": "search_planning",
                    "claim_id": claim.claim_id,
                    "input_tokens": search_plan_output.raw_response.input_tokens,
                    "output_tokens": search_plan_output.raw_response.output_tokens,
                },
            )
            self.audit.record_cost(
                case_id=case.case_id,
                cost_type=CostType.AGENT,
                provider=search_plan_output.raw_response.provider,
                units=search_plan_output.raw_response.input_tokens
                + search_plan_output.raw_response.output_tokens,
                unit_name="token",
                estimated_cost_usd=search_plan_output.raw_response.estimated_cost_usd,
                metadata={"agent_name": self.search_planning_agent.name},
            )

            budget_decision = self.search_budget_controller.decide(search_plan)

            self.audit.record_agent_run(
                case_id=case.case_id,
                agent_name="search_budget_controller",
                provider="internal_deterministic",
                input_data=search_plan,
                output_data=budget_decision,
                metadata={
                    "stage": "search_budgeting",
                    "claim_id": claim.claim_id,
                    "allowed_query_count": len(budget_decision.allowed_queries),
                    "blocked_query_count": len(budget_decision.blocked_queries),
                    "reason": budget_decision.reason,
                },
            )

            search_results: list[SearchResult] = []

            for query in budget_decision.allowed_queries:
                provider = self._get_provider_for_query(query)

                if provider.name == "no_search_provider":
                    self.audit.record_agent_run(
                        case_id=case.case_id,
                        agent_name=provider.name,
                        provider=provider.name,
                        input_data=query,
                        output_data={
                            "skipped": True,
                            "reason": "No free external search provider is configured.",
                        },
                        metadata={
                            "stage": "skipped_search",
                            "claim_id": claim.claim_id,
                            "query_id": query.query_id,
                            "cost_tier": query.cost_tier,
                        },
                    )
                    continue

                query_results = provider.search(query)
                search_results.extend(query_results)

                self.audit.record_agent_run(
                    case_id=case.case_id,
                    agent_name=provider.name,
                    provider=provider.name,
                    input_data=query,
                    output_data=query_results,
                    metadata={
                        "stage": "search",
                        "claim_id": claim.claim_id,
                        "query_id": query.query_id,
                        "cost_tier": query.cost_tier,
                        "result_count": len(query_results) if "query_results" in locals() else len(search_results),
                    },
                )
                self.audit.record_cost(
                    case_id=case.case_id,
                    cost_type=CostType.SEARCH,
                    provider=provider.name,
                    units=1 if query.cost_tier == "paid" else 0,
                    unit_name="search_call",
                    estimated_cost_usd=0.0,
                    metadata={
                        "query_id": query.query_id,
                        "query": query.query,
                        "cost_tier": query.cost_tier,
                    },
                )

            for blocked_query in budget_decision.blocked_queries:
                self.audit.record_agent_run(
                    case_id=case.case_id,
                    agent_name="search_budget_controller",
                    provider="internal_deterministic",
                    input_data=blocked_query,
                    output_data={
                        "blocked": True,
                        "reason": budget_decision.reason,
                    },
                    metadata={
                        "stage": "blocked_search_query",
                        "claim_id": claim.claim_id,
                        "query_id": blocked_query.query_id,
                        "cost_tier": blocked_query.cost_tier,
                    },
                )

            direct_source_fetch_input = DirectSourceFetchInput(
                claim=claim,
                search_plan=search_plan,
            )
            direct_source_fetch_output = self.direct_source_fetch_agent.run(
                direct_source_fetch_input
            )
            search_results.extend(direct_source_fetch_output.results)

            self.audit.record_agent_run(
                case_id=case.case_id,
                agent_name=self.direct_source_fetch_agent.name,
                provider="direct_http_fetch",
                input_data=direct_source_fetch_input,
                output_data=direct_source_fetch_output,
                metadata={
                    "stage": "direct_source_fetch",
                    "claim_id": claim.claim_id,
                    "result_count": len(direct_source_fetch_output.results),
                    "skipped_count": len(direct_source_fetch_output.skipped_candidates),
                    "expanded_url_count": len(direct_source_fetch_output.expanded_urls),
                    "failed_url_count": len(direct_source_fetch_output.failed_urls),
                    "expanded_urls": direct_source_fetch_output.expanded_urls[:10],
                    "failed_urls": direct_source_fetch_output.failed_urls[:10],
                },
            )
            self.audit.record_cost(
                case_id=case.case_id,
                cost_type=CostType.SEARCH,
                provider="direct_http_fetch",
                units=0,
                unit_name="fetch_call",
                estimated_cost_usd=0.0,
                metadata={
                    "agent_name": self.direct_source_fetch_agent.name,
                    "claim_id": claim.claim_id,
                    "result_count": len(direct_source_fetch_output.results),
                },
            )

            page_fetch_input = SearchResultPageFetchInput(
                claim=claim,
                search_results=search_results,
            )
            page_fetch_output = self.search_result_page_fetch_agent.run(
                page_fetch_input
            )
            search_results = page_fetch_output.results

            self.audit.record_agent_run(
                case_id=case.case_id,
                agent_name=self.search_result_page_fetch_agent.name,
                provider="direct_http_fetch",
                input_data=page_fetch_input,
                output_data=page_fetch_output,
                metadata={
                    "stage": "search_result_page_fetch",
                    "claim_id": claim.claim_id,
                    "input_result_count": len(page_fetch_input.search_results),
                    "output_result_count": len(page_fetch_output.results),
                    "fetched_count": page_fetch_output.fetched_count,
                    "skipped_count": page_fetch_output.skipped_count,
                    "failed_count": len(page_fetch_output.failed_urls),
                },
            )
            self.audit.record_cost(
                case_id=case.case_id,
                cost_type=CostType.SEARCH,
                provider="direct_http_fetch",
                units=page_fetch_output.fetched_count,
                unit_name="fetch_call",
                estimated_cost_usd=0.0,
                metadata={
                    "agent_name": self.search_result_page_fetch_agent.name,
                    "claim_id": claim.claim_id,
                },
            )

            provided_text_input = ProvidedTextEvidenceInput(
                claim=claim,
                case_input_type=case.input_type,
                case_input_text=investigation_input_text,
                case_title=(
                    fetched_url.title
                    if fetched_url is not None and fetched_url.title
                    else case.title
                ),
                source_url=(
                    fetched_url.final_url
                    if fetched_url is not None and fetched_url.final_url
                    else case.input_text if case.input_type == InputType.URL else None
                ),
            )
            provided_text_evidence = self.provided_text_evidence_agent.run(
                provided_text_input
            )

            self.audit.record_agent_run(
                case_id=case.case_id,
                agent_name=self.provided_text_evidence_agent.name,
                provider="internal_deterministic",
                input_data=provided_text_input,
                output_data=provided_text_evidence,
                metadata={
                    "stage": "provided_text_evidence",
                    "claim_id": claim.claim_id,
                    "evidence_count": len(provided_text_evidence),
                },
            )
            self.audit.record_cost(
                case_id=case.case_id,
                cost_type=CostType.AGENT,
                provider="internal_deterministic",
                units=1,
                unit_name="agent_call",
                estimated_cost_usd=0.0,
                metadata={"agent_name": self.provided_text_evidence_agent.name},
            )

            source_assessment_input = PlannerSourceAssessmentInput(
                claim=claim,
                search_plan=search_plan,
                search_results=search_results,
            )
            source_assessment_output = self.source_assessment_agent.run(
                source_assessment_input
            )

            self.audit.record_agent_run(
                case_id=case.case_id,
                agent_name=self.source_assessment_agent.name,
                provider="internal_planner_driven",
                input_data=source_assessment_input,
                output_data=source_assessment_output,
                metadata={
                    "stage": "source_assessment",
                    "claim_id": claim.claim_id,
                    "result_count": len(search_results),
                },
            )
            self.audit.record_cost(
                case_id=case.case_id,
                cost_type=CostType.AGENT,
                provider="internal_planner_driven",
                units=1,
                unit_name="agent_call",
                estimated_cost_usd=0.0,
                metadata={"agent_name": self.source_assessment_agent.name},
            )

            evidence_input = SearchEvidenceInput(
                claim=claim,
                search_results=source_assessment_output.assessed_results,
            )
            search_evidence = self.evidence_agent.run(evidence_input)
            claim_evidence = provided_text_evidence + search_evidence
            evidence_items.extend(claim_evidence)

            self.audit.record_agent_run(
                case_id=case.case_id,
                agent_name=self.evidence_agent.name,
                provider="internal_deterministic",
                input_data=evidence_input,
                output_data=search_evidence,
                metadata={
                    "stage": "evidence_extraction",
                    "claim_id": claim.claim_id,
                    "evidence_count": len(search_evidence),
                },
            )
            self.audit.record_cost(
                case_id=case.case_id,
                cost_type=CostType.AGENT,
                provider="internal_deterministic",
                units=1,
                unit_name="agent_call",
                estimated_cost_usd=0.0,
                metadata={"agent_name": self.evidence_agent.name},
            )

            claim_stances: list[StanceResult] = []

            raw_claim_evidence_count = len(claim_evidence)
            claim_evidence, evidence_quality_decisions = filter_evidence_items(
                claim=claim,
                evidence_items=claim_evidence,
            )

            evidence_items = [
                evidence
                for evidence in evidence_items
                if evidence.claim_id != claim.claim_id
            ] + claim_evidence

            self.audit.record_agent_run(
                case_id=case.case_id,
                agent_name="evidence_quality_filter",
                provider="internal_algorithm",
                input_data={
                    "claim_id": claim.claim_id,
                    "raw_evidence_count": raw_claim_evidence_count,
                },
                output_data={
                    "kept_evidence_count": len(claim_evidence),
                    "decisions": evidence_quality_decisions,
                },
                metadata={
                    "stage": "evidence_quality_filter",
                    "claim_id": claim.claim_id,
                    "raw_evidence_count": raw_claim_evidence_count,
                    "kept_evidence_count": len(claim_evidence),
                    "discarded_evidence_count": raw_claim_evidence_count - len(claim_evidence),
                },
            )

            for evidence in claim_evidence:
                stance_input = LLMStanceInput(
                    claim=claim,
                    evidence=evidence,
                )
                try:
                    stance_output = self.stance_agent.run(stance_input)
                except Exception as error:
                    self._fail_case_due_to_upstream_llm_error(
                        case=running_case,
                        stage="stance_classification",
                        agent_name=self.stance_agent.name,
                        error=error,
                        input_data=stance_input,
                        claim_id=claim.claim_id,
                        evidence_id=evidence.evidence_id,
                    )
                stance = stance_output.stance
                stance_results.append(stance)
                claim_stances.append(stance)

                self.audit.record_agent_run(
                    case_id=case.case_id,
                    agent_name=self.stance_agent.name,
                    provider=stance_output.raw_response.provider,
                    model=stance_output.raw_response.model,
                    input_data=stance_input,
                    output_data=stance_output,
                    metadata={
                        "stage": "stance_classification",
                        "claim_id": claim.claim_id,
                        "evidence_id": evidence.evidence_id,
                        "input_tokens": stance_output.raw_response.input_tokens,
                        "output_tokens": stance_output.raw_response.output_tokens,
                    },
                )
                self.audit.record_cost(
                    case_id=case.case_id,
                    cost_type=CostType.AGENT,
                    provider=stance_output.raw_response.provider,
                    units=stance_output.raw_response.input_tokens
                    + stance_output.raw_response.output_tokens,
                    unit_name="token",
                    estimated_cost_usd=stance_output.raw_response.estimated_cost_usd,
                    metadata={"agent_name": self.stance_agent.name},
                )

            source_reliability_service = getattr(
                self,
                "source_reliability_service",
                SourceReliabilityService(),
            )
            source_reliability_service.apply_to_evidence_items(
                evidence_items=claim_evidence,
                claim_type=getattr(claim.claim_type, "value", str(claim.claim_type)),
                topic="eval:nba",
            )

            source_reliability_service = getattr(
                self,
                "source_reliability_service",
                SourceReliabilityService(),
            )
            source_reliability_service.apply_to_evidence_items(
                evidence_items=claim_evidence,
                claim_type=getattr(claim.claim_type, "value", str(claim.claim_type)),
                topic="eval:nba",
            )

            claim_verdict = score_claim(
                claim_id=claim.claim_id,
                evidence_items=claim_evidence,
                stance_results=claim_stances,
            )
            verdicts.append(claim_verdict)

            self.audit.record_agent_run(
                case_id=case.case_id,
                agent_name="pivot_scoring",
                provider="internal_algorithm",
                input_data={
                    "claim_id": claim.claim_id,
                    "evidence_count": len(claim_evidence),
                    "stance_count": len(claim_stances),
                },
                output_data=claim_verdict,
                metadata={
                    "stage": "pivot_scoring",
                    "claim_id": claim.claim_id,
                },
            )

            correction_input = ClaimCorrectionInput(
                claim=claim,
                evidence=claim_evidence,
                stances=claim_stances,
                verdict=claim_verdict,
            )
            correction_agent = getattr(
                self,
                "correction_agent",
                ClaimCorrectionAgent(),
            )
            correction_output = correction_agent.run(correction_input)
            correction = correction_output.correction
            corrections.append(correction)

            self.audit.record_agent_run(
                case_id=case.case_id,
                agent_name=correction_agent.name,
                provider="internal_deterministic",
                input_data=correction_input,
                output_data=correction_output,
                metadata={
                    "stage": "claim_correction",
                    "claim_id": claim.claim_id,
                    "needs_correction": correction.needs_correction,
                },
            )
            self.audit.record_cost(
                case_id=case.case_id,
                cost_type=CostType.AGENT,
                provider="internal_deterministic",
                units=1,
                unit_name="agent_call",
                estimated_cost_usd=0.0,
                metadata={"agent_name": correction_agent.name},
            )

            saved_verified_claim = self.verified_claims.save_if_reusable(
                claim=claim,
                verdict=claim_verdict,
                evidence_count=len(claim_evidence),
                evidence_items=claim_evidence,
                stance_results=claim_stances,
            )

            self.audit.record_agent_run(
                case_id=case.case_id,
                agent_name="verified_claim_store",
                provider="internal_repository",
                input_data={
                    "claim": claim,
                    "verdict": claim_verdict,
                    "evidence_count": len(claim_evidence),
                },
                output_data=saved_verified_claim,
                metadata={
                    "stage": "verified_claim_store",
                    "claim_id": claim.claim_id,
                    "stored": saved_verified_claim is not None,
                },
            )

        case_verdict = self._aggregate_case_verdict(verdicts)
        case_confidence = self._aggregate_case_confidence(verdicts)

        report_input = ReportAgentInput(
            title=case.title or "Untitled Investigation",
            input_text=case.input_text,
            case_verdict=case_verdict,
            confidence=case_confidence,
            claims=claims,
            evidence=evidence_items,
            verdicts=verdicts,
        )
        report = self.report_agent.run(report_input)

        self.audit.record_agent_run(
            case_id=case.case_id,
            agent_name=self.report_agent.name,
            provider="internal_deterministic",
            input_data=report_input,
            output_data=report,
            metadata={"stage": "report_generation"},
        )
        self.audit.record_cost(
            case_id=case.case_id,
            cost_type=CostType.AGENT,
            provider="internal_deterministic",
            units=1,
            unit_name="agent_call",
            estimated_cost_usd=0.0,
            metadata={"agent_name": self.report_agent.name},
        )

        audit_trail = self.audit.get_trail(case.case_id)

        result = InvestigationResult(
            case_id=case.case_id,
            status=CaseStatus.COMPLETED,
            case_verdict=case_verdict,
            confidence=case_confidence,
            claims=claims,
            evidence=evidence_items,
            stances=stance_results,
            verdicts=verdicts,
            corrections=corrections,
            report=report,
            agent_runs=audit_trail.agent_runs,
            cost_logs=audit_trail.cost_logs,
        )

        completed_case = running_case.model_copy(
            update={
                "status": CaseStatus.COMPLETED,
                "updated_at": utc_now(),
            }
        )
        self.case_repo.update(completed_case)

        return self.investigation_repo.save(result)

    def _fail_case_due_to_upstream_llm_error(
        self,
        case,
        stage: str,
        agent_name: str,
        error: Exception,
        input_data,
        claim_id: str | None = None,
        evidence_id: str | None = None,
    ) -> None:
        upstream_status = getattr(error, "status_code", None)
        error_type = type(error).__name__
        error_message = str(error)

        failed_case = case.model_copy(
            update={
                "status": CaseStatus.FAILED,
                "updated_at": utc_now(),
            }
        )
        self.case_repo.update(failed_case)

        metadata = {
            "stage": stage,
            "failed": True,
            "error_type": error_type,
            "error_message": error_message,
            "upstream_status": upstream_status,
        }

        if claim_id is not None:
            metadata["claim_id"] = claim_id

        if evidence_id is not None:
            metadata["evidence_id"] = evidence_id

        self.audit.record_agent_run(
            case_id=case.case_id,
            agent_name=agent_name,
            provider="upstream_llm",
            input_data=input_data,
            output_data={
                "failed": True,
                "error_type": error_type,
                "error_message": error_message,
                "upstream_status": upstream_status,
            },
            metadata=metadata,
        )

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": "Upstream LLM provider is unavailable or rate-limited.",
                "case_id": case.case_id,
                "stage": stage,
                "agent_name": agent_name,
                "error_type": error_type,
                "upstream_status": upstream_status,
                "error_message": error_message,
            },
        )

    def get_result(self, case_id: str) -> InvestigationResult:
        result = self.investigation_repo.get(case_id)

        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Investigation result not found: {case_id}",
            )

        return result

    def _rehydrate_cached_evidence(
        self,
        claim,
        cached_record,
    ) -> tuple[list[EvidenceItem], dict[str, str]]:
        evidence_items: list[EvidenceItem] = []
        evidence_id_map: dict[str, str] = {}

        for index, cached_evidence in enumerate(
            cached_record.evidence_snapshot,
            start=1,
        ):
            old_evidence_id = cached_evidence.evidence_id
            new_evidence_id = f"{claim.claim_id}_cached_evidence_{index}"
            evidence_id_map[old_evidence_id] = new_evidence_id

            data = cached_evidence.model_dump()
            data["claim_id"] = claim.claim_id
            data["evidence_id"] = new_evidence_id
            data["source_id"] = f"cached::{data.get('source_id', 'unknown')}"

            evidence_items.append(EvidenceItem.model_validate(data))

        return evidence_items, evidence_id_map

    def _rehydrate_cached_stances(
        self,
        claim,
        cached_record,
        evidence_id_map: dict[str, str],
    ) -> list[StanceResult]:
        stances: list[StanceResult] = []

        for cached_stance in cached_record.stance_snapshot:
            data = cached_stance.model_dump()

            if "claim_id" in data:
                data["claim_id"] = claim.claim_id

            if "evidence_id" in data:
                data["evidence_id"] = evidence_id_map.get(
                    data["evidence_id"],
                    data["evidence_id"],
                )

            stances.append(StanceResult.model_validate(data))

        return stances

    def _get_provider_for_query(self, query: SearchQuery) -> SearchProvider:
        provider_name = (query.provider or "").strip().lower()

        if query.cost_tier == "paid":
            return self.paid_search_provider

        if provider_name in {
            "",
            "mock",
            "configured_free_provider",
            "free",
            "default",
        }:
            return self.free_search_provider

        if provider_name in {
            "configured_paid_provider",
            "paid",
        }:
            return self.paid_search_provider

        return self.free_search_provider


    def _aggregate_case_verdict(
        self,
        verdicts: list[PivotVerdict],
    ) -> VerdictLabel | None:
        if not verdicts:
            return None

        labels = [verdict.verdict for verdict in verdicts]

        if VerdictLabel.CONTRADICTED in labels:
            return VerdictLabel.CONTRADICTED

        if VerdictLabel.CONTESTED in labels:
            return VerdictLabel.CONTESTED

        if VerdictLabel.UNVERIFIABLE in labels:
            return VerdictLabel.UNVERIFIABLE

        if VerdictLabel.PARTIALLY_SUPPORTED in labels:
            return VerdictLabel.PARTIALLY_SUPPORTED

        if all(label == VerdictLabel.SUPPORTED for label in labels):
            return VerdictLabel.SUPPORTED

        return VerdictLabel.PARTIALLY_SUPPORTED

    def _aggregate_case_confidence(self, verdicts: list[PivotVerdict]) -> float | None:
        if not verdicts:
            return None

        total = sum(verdict.confidence for verdict in verdicts)
        return round(total / len(verdicts), 4)


investigation_service = InvestigationService(
    case_repo=case_repository,
    investigation_repo=investigation_repository,
    audit=audit_service,
    verified_claims=verified_claim_service,
)
