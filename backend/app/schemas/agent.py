from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.constants import ClaimType, SourceType, StanceLabel, VerdictLabel


class AtomicClaim(BaseModel):
    claim_id: str
    claim_text: str
    claim_type: ClaimType = ClaimType.UNKNOWN

    subject: str | None = None
    predicate: str | None = None
    object: str | None = None

    event_time: datetime | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class SourceProfile(BaseModel):
    source_id: str
    domain: str
    source_name: str | None = None
    source_type: SourceType = SourceType.UNKNOWN

    reliability_prior: float = Field(default=0.5, ge=0.0, le=1.0)
    topic_expertise: list[str] = Field(default_factory=list)
    independence_score: float = Field(default=0.5, ge=0.0, le=1.0)


class EvidenceItem(BaseModel):
    evidence_id: str
    claim_id: str
    source_id: str

    url: str | None = None
    title: str | None = None
    author: str | None = None

    published_at: datetime | None = None
    retrieved_at: datetime | None = None

    evidence_text: str
    independence_group: str | None = None

    reliability: float = Field(default=0.5, ge=0.0, le=1.0)
    independence: float = Field(default=0.5, ge=0.0, le=1.0)
    freshness: float = Field(default=0.5, ge=0.0, le=1.0)
    specificity: float = Field(default=0.5, ge=0.0, le=1.0)

    metadata: dict[str, Any] = Field(default_factory=dict)

    metadata: dict[str, Any] = Field(default_factory=dict)


class StanceResult(BaseModel):
    claim_id: str
    evidence_id: str
    stance: StanceLabel
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class PivotVerdict(BaseModel):
    claim_id: str
    verdict: VerdictLabel
    confidence: float = Field(ge=0.0, le=1.0)

    support_score: float = Field(ge=0.0)
    contradiction_score: float = Field(ge=0.0)
    uncertainty_score: float = Field(ge=0.0)

    reason: str
    debug: dict[str, Any] = Field(default_factory=dict)
