from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import SourceType
from app.domain.cases.models import utc_now


class SourceCandidate(BaseModel):
    name: str | None = None
    domain: str | None = None
    url: str | None = None
    expected_source_type: SourceType = SourceType.UNKNOWN
    rationale: str
    priority: int = Field(default=5, ge=1, le=10)


class SearchQuery(BaseModel):
    query_id: str
    claim_id: str
    query: str
    purpose: str

    # free, paid, or unknown
    cost_tier: str = "free"

    # Planner hints. Provider should not infer these by itself.
    expected_source_type: SourceType = SourceType.UNKNOWN
    target_domains: list[str] = Field(default_factory=list)
    provider: str = "mock"


class SearchPlan(BaseModel):
    claim_id: str
    source_candidates: list[SourceCandidate] = Field(default_factory=list)
    queries: list[SearchQuery] = Field(default_factory=list)

    should_use_paid_search: bool = False
    paid_search_rationale: str | None = None
    max_paid_search_calls: int = 0


class SearchResult(BaseModel):
    result_id: str
    query_id: str

    title: str
    url: str
    snippet: str

    source_name: str | None = None
    domain: str | None = None

    # Provider returns neutral metadata.
    # Source assessment agent can update this later.
    source_type: SourceType = SourceType.UNKNOWN

    published_at: datetime | None = None
    retrieved_at: datetime = Field(default_factory=utc_now)

    reliability: float = Field(default=0.5, ge=0.0, le=1.0)
    independence: float = Field(default=0.5, ge=0.0, le=1.0)
    freshness: float = Field(default=0.5, ge=0.0, le=1.0)
    specificity: float = Field(default=0.5, ge=0.0, le=1.0)
