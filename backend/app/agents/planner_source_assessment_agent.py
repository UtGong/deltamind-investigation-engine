from urllib.parse import urlparse

from pydantic import BaseModel, Field

from app.agents.base import Agent
from app.core.constants import SourceType
from app.schemas.agent import AtomicClaim
from app.schemas.search import SearchPlan, SearchQuery, SearchResult, SourceCandidate


class SourceAssessmentNote(BaseModel):
    result_id: str
    domain: str | None = None
    assigned_source_type: SourceType
    reliability: float
    rationale: str
    matched_planner_candidate: str | None = None
    matched_query_id: str | None = None


class PlannerSourceAssessmentInput(BaseModel):
    claim: AtomicClaim
    search_plan: SearchPlan
    search_results: list[SearchResult]


class PlannerSourceAssessmentOutput(BaseModel):
    assessed_results: list[SearchResult]
    notes: list[SourceAssessmentNote] = Field(default_factory=list)


class PlannerSourceAssessmentAgent(
    Agent[PlannerSourceAssessmentInput, PlannerSourceAssessmentOutput]
):
    name = "planner_source_assessment_agent"

    def run(
        self,
        input_data: PlannerSourceAssessmentInput,
    ) -> PlannerSourceAssessmentOutput:
        queries_by_id = {
            query.query_id: query
            for query in input_data.search_plan.queries
        }

        assessed_results: list[SearchResult] = []
        notes: list[SourceAssessmentNote] = []

        for result in input_data.search_results:
            query = queries_by_id.get(result.query_id)
            candidate = self._match_candidate(
                result=result,
                candidates=input_data.search_plan.source_candidates,
            )

            assigned_source_type = self._assign_source_type(
                query=query,
                candidate=candidate,
            )

            reliability = self._assign_reliability(
                source_type=assigned_source_type,
                candidate=candidate,
            )

            rationale = self._build_rationale(
                result=result,
                query=query,
                candidate=candidate,
                assigned_source_type=assigned_source_type,
            )

            assessed_result = result.model_copy(
                update={
                    "source_type": assigned_source_type,
                    "reliability": reliability,
                }
            )

            assessed_results.append(assessed_result)
            notes.append(
                SourceAssessmentNote(
                    result_id=result.result_id,
                    domain=result.domain,
                    assigned_source_type=assigned_source_type,
                    reliability=reliability,
                    rationale=rationale,
                    matched_planner_candidate=(
                        candidate.domain or candidate.url or candidate.name
                        if candidate is not None
                        else None
                    ),
                    matched_query_id=query.query_id if query is not None else None,
                )
            )

        return PlannerSourceAssessmentOutput(
            assessed_results=assessed_results,
            notes=notes,
        )

    def _match_candidate(
        self,
        result: SearchResult,
        candidates: list[SourceCandidate],
    ) -> SourceCandidate | None:
        result_domain = self._normalize_domain(result.domain or result.url)

        if not result_domain:
            return None

        for candidate in sorted(candidates, key=lambda item: item.priority):
            candidate_domain = self._normalize_domain(candidate.domain or candidate.url)

            if not candidate_domain:
                continue

            if self._domain_matches(result_domain, candidate_domain):
                return candidate

        return None

    def _assign_source_type(
        self,
        query: SearchQuery | None,
        candidate: SourceCandidate | None,
    ) -> SourceType:
        if candidate is not None and candidate.expected_source_type != SourceType.UNKNOWN:
            return candidate.expected_source_type

        if query is not None and query.expected_source_type != SourceType.UNKNOWN:
            return query.expected_source_type

        return SourceType.UNKNOWN

    def _assign_reliability(
        self,
        source_type: SourceType,
        candidate: SourceCandidate | None,
    ) -> float:
        # This is source-type policy, not domain authority.
        # Domain-specific authority must come from the planner, not this agent.
        base_by_type = {
            SourceType.OFFICIAL: 0.90,
            SourceType.PRIMARY: 0.86,
            SourceType.DATABASE: 0.80,
            SourceType.TRUSTED_MEDIA: 0.74,
            SourceType.MEDIA: 0.60,
            SourceType.AGGREGATOR: 0.50,
            SourceType.SOCIAL: 0.35,
            SourceType.UNKNOWN: 0.50,
        }

        base = base_by_type.get(source_type, 0.50)

        if candidate is None:
            return round(base * 0.90, 4)

        priority_boost = max(0.0, (10 - candidate.priority) * 0.005)
        return round(min(0.95, base + priority_boost), 4)

    def _build_rationale(
        self,
        result: SearchResult,
        query: SearchQuery | None,
        candidate: SourceCandidate | None,
        assigned_source_type: SourceType,
    ) -> str:
        if candidate is not None:
            return (
                f"Assigned {assigned_source_type} because the result domain matched "
                f"a planner-proposed source candidate. Planner rationale: "
                f"{candidate.rationale}"
            )

        if query is not None and query.expected_source_type != SourceType.UNKNOWN:
            return (
                f"Assigned {assigned_source_type} from the planner's expected source "
                f"type for query {query.query_id}. No domain-specific authority was "
                f"hardcoded by the provider."
            )

        return (
            "No planner source candidate or expected source type matched this result; "
            "source type remains unknown."
        )

    def _normalize_domain(self, value: str | None) -> str | None:
        if value is None:
            return None

        cleaned = value.strip().lower()

        if not cleaned:
            return None

        if "://" in cleaned:
            parsed = urlparse(cleaned)
            cleaned = parsed.netloc

        return cleaned.removeprefix("www.") or None

    def _domain_matches(self, result_domain: str, candidate_domain: str) -> bool:
        return (
            result_domain == candidate_domain
            or result_domain.endswith(f".{candidate_domain}")
        )
