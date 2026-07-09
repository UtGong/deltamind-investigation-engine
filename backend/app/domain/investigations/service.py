from typing import Any

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
from app.agents.score_facts import extract_score_fact, infer_score_stance
from app.agents.url_fetch_agent import UrlFetchAgent, UrlFetchInput, UrlFetchOutput
from app.algorithm.pivot.scoring import PivotThresholds, score_claim
from app.domain.source_reliability.service import SourceReliabilityService
from app.domain.source_independence.service import SourceIndependenceService
from app.algorithm.pivot.evidence_quality import filter_evidence_items
from app.core.config import get_settings
from app.core.constants import CaseStatus, CostType, InputType, VerdictLabel
from app.domain.audit.service import AuditService, audit_service
from app.domain.evidence_graph.service import EvidenceGraphBuilder
from app.domain.trust_certificates.service import TrustCertificateBuilder
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
from app.schemas.agent import AtomicClaim, EvidenceItem, PivotVerdict, StanceResult
from app.schemas.api import InvestigationResult, VerificationError, VerificationStateResponse
from app.schemas.correction import ClaimCorrection
from app.schemas.search import SearchPlan, SearchQuery, SearchResult


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
        self.llm_provider = llm_provider

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

            if cached_record is not None and not self._should_refresh_cached_claim(
                claim=claim,
                cached_record=cached_record,
            ):
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

            search_plan_input = self.search_planning_input_model(
                claim=claim,
                case_context=investigation_input_text,
            )
            search_planning_agent_name = self.search_planning_agent.name
            try:
                search_plan_output = self.search_planning_agent.run(search_plan_input)
            except Exception as error:
                fallback_search_planning_agent = CostAwareSearchPlanningAgent()
                fallback_search_plan_input = CostAwareSearchPlanningInput(
                    claim=claim,
                    case_context=investigation_input_text,
                )
                search_plan_output = fallback_search_planning_agent.run(
                    fallback_search_plan_input
                )
                search_plan_output.raw_response.metadata.update(
                    {
                        "fallback_used": True,
                        "fallback_reason": "llm_search_planning_error",
                        "error_type": type(error).__name__,
                        "error_message": str(error),
                    }
                )
                search_plan_input = fallback_search_plan_input
                search_planning_agent_name = fallback_search_planning_agent.name
            search_plan = search_plan_output.search_plan

            self.audit.record_agent_run(
                case_id=case.case_id,
                agent_name=search_planning_agent_name,
                provider=search_plan_output.raw_response.provider,
                model=search_plan_output.raw_response.model,
                input_data=search_plan_input,
                output_data=search_plan_output,
                metadata={
                    "stage": "search_planning",
                    "claim_id": claim.claim_id,
                    "input_tokens": search_plan_output.raw_response.input_tokens,
                    "output_tokens": search_plan_output.raw_response.output_tokens,
                    "source_candidates": [
                        candidate.model_dump(mode="json")
                        for candidate in search_plan.source_candidates
                    ],
                    "queries": [
                        query.model_dump(mode="json")
                        for query in search_plan.queries
                    ],
                    "should_use_paid_search": search_plan.should_use_paid_search,
                    "paid_search_rationale": search_plan.paid_search_rationale,
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
            empty_free_search_count = 0
            attempted_free_search_count = 0
            stopped_for_paid_recovery = False

            for query in budget_decision.allowed_queries:
                query_results = self._run_search_query(
                    case=case,
                    claim=claim,
                    query=query,
                )
                search_results.extend(query_results)

                if query.cost_tier != "paid":
                    attempted_free_search_count += 1
                    if not query_results:
                        empty_free_search_count += 1

                if self._should_stop_free_search_for_paid_recovery(
                    query=query,
                    search_results=search_results,
                    empty_free_search_count=empty_free_search_count,
                    attempted_free_search_count=attempted_free_search_count,
                ):
                    stopped_for_paid_recovery = True
                    self.audit.record_agent_run(
                        case_id=case.case_id,
                        agent_name="search_budget_controller",
                        provider="internal_deterministic",
                        input_data=query,
                        output_data={
                            "stopped": True,
                            "reason": (
                                "Configured free search returned no results; "
                                "moving to paid recovery instead of exhausting "
                                "all free queries."
                            ),
                        },
                        metadata={
                            "stage": "free_search_early_stop",
                            "claim_id": claim.claim_id,
                            "query_id": query.query_id,
                            "empty_free_search_count": empty_free_search_count,
                        },
                    )
                    break

            if not search_results or stopped_for_paid_recovery:
                search_results.extend(
                    self._run_paid_search_recovery(
                        case=case,
                        claim=claim,
                        search_plan=search_plan,
                        allowed_queries=budget_decision.allowed_queries,
                    )
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

            if self._should_run_direct_source_fetch(search_results, search_plan):
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
            else:
                self.audit.record_agent_run(
                    case_id=case.case_id,
                    agent_name=self.direct_source_fetch_agent.name,
                    provider="direct_http_fetch",
                    input_data={
                        "claim_id": claim.claim_id,
                        "search_result_count": len(search_results),
                    },
                    output_data={
                        "skipped": True,
                        "reason": (
                            "Search provider already returned results and planner "
                            "did not provide exact source URLs."
                        ),
                    },
                    metadata={
                        "stage": "direct_source_fetch_skipped",
                        "claim_id": claim.claim_id,
                        "result_count": len(search_results),
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
            claim_evidence = self._prioritize_evidence_for_stance(
                claim=claim,
                evidence_items=claim_evidence,
            )

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

                if self._has_decisive_score_stance(claim=claim, stance=stance):
                    self.audit.record_agent_run(
                        case_id=case.case_id,
                        agent_name=self.stance_agent.name,
                        provider="internal_deterministic",
                        input_data={
                            "claim_id": claim.claim_id,
                            "evidence_id": evidence.evidence_id,
                        },
                        output_data={
                            "stopped": True,
                            "reason": (
                                "A high-confidence deterministic score stance "
                                "is sufficient for pivot scoring."
                            ),
                        },
                        metadata={
                            "stage": "stance_classification_early_stop",
                            "claim_id": claim.claim_id,
                            "evidence_id": evidence.evidence_id,
                            "stance": getattr(stance.stance, "value", str(stance.stance)),
                            "confidence": stance.confidence,
                        },
                    )
                    break

            source_reliability_service = getattr(
                self,
                "source_reliability_service",
                SourceReliabilityService(),
            )
            source_reliability_service.apply_to_evidence_items(
                evidence_items=claim_evidence,
                claim_type=getattr(claim.claim_type, "value", str(claim.claim_type)),
                topic=getattr(claim.claim_type, "value", str(claim.claim_type)),
            )

            source_independence_service = getattr(
                self,
                "source_independence_service",
                SourceIndependenceService(),
            )
            source_independence_service.apply_to_evidence_items(
                evidence_items=claim_evidence,
            )

            claim_verdict = score_claim(
                claim_id=claim.claim_id,
                evidence_items=claim_evidence,
                stance_results=claim_stances,
                thresholds=self._pivot_thresholds_for_claim(claim),
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
                ClaimCorrectionAgent(llm_provider=self.llm_provider),
            )
            correction_output = correction_agent.run(correction_input)
            correction = correction_output.correction
            corrections.append(correction)

            self.audit.record_agent_run(
                case_id=case.case_id,
                agent_name=correction_agent.name,
                provider=(
                    correction_output.raw_response.provider
                    if correction_output.raw_response is not None
                    else "llm_correction_unavailable"
                ),
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

        evidence_graph = EvidenceGraphBuilder().build(
            case_id=case.case_id,
            claims=claims,
            evidence_items=evidence_items,
            stance_results=stance_results,
            verdicts=verdicts,
        )

        trust_certificate = TrustCertificateBuilder().build(
            case_id=case.case_id,
            overall_verdict=getattr(case_verdict, 'value', str(case_verdict)),
            confidence=case_confidence,
            claims=claims,
            evidence_items=evidence_items,
            verdicts=verdicts,
            evidence_graph=evidence_graph,
        )

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
            evidence_graph=evidence_graph,
            trust_certificate=trust_certificate,
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


    def mark_case_running(self, case_id: str):
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
        return self.case_repo.update(running_case)

    def mark_case_failed(
        self,
        *,
        case_id: str,
        stage: str,
        error: Exception,
        agent_name: str = "background_investigation",
    ) -> None:
        case = self.case_repo.get(case_id)

        if case is not None:
            failed_case = case.model_copy(
                update={
                    "status": CaseStatus.FAILED,
                    "updated_at": utc_now(),
                }
            )
            self.case_repo.update(failed_case)

        error_type = type(error).__name__
        error_message = str(error)
        upstream_status = getattr(error, "status_code", None)
        detail = getattr(error, "detail", None)

        self.audit.record_agent_run(
            case_id=case_id,
            agent_name=agent_name,
            provider="backend",
            input_data={"case_id": case_id},
            output_data={
                "failed": True,
                "detail": detail,
                "error_type": error_type,
                "error_message": error_message,
                "upstream_status": upstream_status,
            },
            metadata={
                "stage": stage,
                "failed": True,
                "error_type": error_type,
                "error_message": error_message,
                "upstream_status": upstream_status,
                "detail": detail,
            },
        )

    def get_verification_state(self, case_id: str) -> VerificationStateResponse:
        case = self.case_repo.get(case_id)

        if case is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Case not found: {case_id}",
            )

        result = self.investigation_repo.get(case_id)
        trust_certificate = result.trust_certificate if result is not None else None
        evidence_graph = result.evidence_graph if result is not None else None
        error = self._latest_error(case_id)

        return VerificationStateResponse(
            case_id=case_id,
            case_available=True,
            case_status=self._frontend_case_status(case.status),
            investigation_available=result is not None,
            certificate_available=trust_certificate is not None,
            evidence_graph_available=evidence_graph is not None,
            error_available=error is not None,
            case={
                "case_id": case.case_id,
                "title": case.title,
                "input_type": case.input_type,
                "input_text": case.input_text,
                "status": case.status,
                "created_at": case.created_at,
                "updated_at": case.updated_at,
            },
            investigation=result,
            trust_certificate=trust_certificate,
            evidence_graph=evidence_graph,
            error=error,
        )

    def _frontend_case_status(self, case_status: CaseStatus) -> str:
        if case_status == CaseStatus.CREATED:
            return "queued"
        return str(case_status)

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


    def _latest_error(self, case_id: str) -> VerificationError | None:
        audit_trail = self.audit.get_trail(case_id)

        for agent_run in reversed(audit_trail.agent_runs):
            metadata: dict[str, Any] = agent_run.metadata or {}
            if metadata.get("failed") is not True:
                continue

            return VerificationError(
                message=str(
                    metadata.get("message")
                    or metadata.get("error_message")
                    or "Investigation failed."
                ),
                case_id=case_id,
                stage=(
                    str(metadata["stage"])
                    if metadata.get("stage") is not None
                    else None
                ),
                agent_name=agent_run.agent_name,
                error_type=(
                    str(metadata["error_type"])
                    if metadata.get("error_type") is not None
                    else None
                ),
                error_message=(
                    str(metadata["error_message"])
                    if metadata.get("error_message") is not None
                    else None
                ),
                upstream_status=(
                    int(metadata["upstream_status"])
                    if metadata.get("upstream_status") is not None
                    else None
                ),
                metadata=metadata,
            )

        return None

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

    def _should_refresh_cached_claim(self, *, claim: AtomicClaim, cached_record) -> bool:
        verdict = getattr(cached_record.verdict, "value", str(cached_record.verdict))
        if verdict != "unverifiable":
            return False

        if extract_score_fact(claim.claim_text) is None:
            return False

        return (
            cached_record.evidence_count == 0
            or len(cached_record.evidence_snapshot or []) == 0
            or len(cached_record.stance_snapshot or []) == 0
        )

    @property
    def paid_search_provider(self) -> SearchProvider:
        if self._paid_search_provider is None:
            self._paid_search_provider = get_paid_search_provider()

        return self._paid_search_provider

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

    def _run_search_query(
        self,
        *,
        case,
        claim: AtomicClaim,
        query: SearchQuery,
    ) -> list[SearchResult]:
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
            return []

        query_results = provider.search(query)

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
                "result_count": len(query_results),
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

        return query_results

    def _should_run_direct_source_fetch(
        self,
        search_results: list[SearchResult],
        search_plan: SearchPlan,
    ) -> bool:
        if not search_results:
            return True

        return any(candidate.url for candidate in search_plan.source_candidates)

    def _should_stop_free_search_for_paid_recovery(
        self,
        *,
        query: SearchQuery,
        search_results: list[SearchResult],
        empty_free_search_count: int,
        attempted_free_search_count: int,
    ) -> bool:
        settings = get_settings()

        return (
            query.cost_tier != "paid"
            and attempted_free_search_count >= 1
            and settings.allow_paid_search
            and settings.max_paid_search_calls_per_case > 0
        )

    def _prioritize_evidence_for_stance(
        self,
        *,
        claim: AtomicClaim,
        evidence_items: list[EvidenceItem],
    ) -> list[EvidenceItem]:
        def score_priority(evidence: EvidenceItem) -> int:
            stance = infer_score_stance(
                claim_text=claim.claim_text,
                evidence_text=f"{evidence.title or ''}\n{evidence.evidence_text}",
            )
            return 0 if stance in {"supports", "contradicts"} else 1

        return sorted(evidence_items, key=score_priority)

    def _has_decisive_score_stance(
        self,
        *,
        claim: AtomicClaim,
        stance: StanceResult,
    ) -> bool:
        if extract_score_fact(claim.claim_text) is None:
            return False

        stance_label = getattr(stance.stance, "value", str(stance.stance))
        return stance_label in {"supports", "contradicts"} and stance.confidence >= 0.88

    def _pivot_thresholds_for_claim(self, claim: AtomicClaim) -> PivotThresholds:
        if extract_score_fact(claim.claim_text) is None:
            return PivotThresholds()

        return PivotThresholds(
            contradicted_min=0.40,
        )

    def _run_paid_search_recovery(
        self,
        *,
        case,
        claim: AtomicClaim,
        search_plan: SearchPlan,
        allowed_queries: list[SearchQuery],
    ) -> list[SearchResult]:
        settings = get_settings()

        if (
            not settings.allow_paid_search
            or settings.max_paid_search_calls_per_case <= 0
        ):
            return []

        seed_queries = [
            query for query in allowed_queries if query.cost_tier != "paid"
        ] or [
            query for query in search_plan.queries if query.cost_tier != "paid"
        ]
        if not seed_queries:
            return []

        max_calls = min(
            settings.max_paid_search_calls_per_case,
            len(seed_queries),
        )
        recovery_results: list[SearchResult] = []

        for index, seed_query in enumerate(seed_queries[:max_calls], start=1):
            paid_query = seed_query.model_copy(
                update={
                    "query_id": f"{seed_query.query_id}_paid_recovery_{index}",
                    "cost_tier": "paid",
                    "provider": "configured_paid_provider",
                    "purpose": (
                        "Paid recovery search after configured free search returned no results. "
                        f"{seed_query.purpose}"
                    ),
                }
            )

            self.audit.record_agent_run(
                case_id=case.case_id,
                agent_name="search_budget_controller",
                provider="internal_deterministic",
                input_data=seed_query,
                output_data=paid_query,
                metadata={
                    "stage": "paid_search_recovery",
                    "claim_id": claim.claim_id,
                    "query_id": seed_query.query_id,
                    "paid_query_id": paid_query.query_id,
                    "reason": "Free search returned no results for the claim.",
                },
            )
            recovery_results.extend(
                self._run_search_query(case=case, claim=claim, query=paid_query)
            )

        return recovery_results

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
