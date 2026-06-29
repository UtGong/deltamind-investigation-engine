from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


CertificateLifecycleStatus = Literal[
    "draft",
    "active",
    "updated",
    "downgraded",
    "revoked",
    "expired",
]


class TrustCertificateClaimSummary(BaseModel):
    claim_id: str
    claim_text: str
    verdict: str | None = None
    confidence: float | None = None
    support_score: float | None = None
    contradiction_score: float | None = None
    uncertainty_score: float | None = None


class TrustCertificateEvidenceSummary(BaseModel):
    evidence_id: str
    claim_id: str
    source_id: str
    url: str | None = None
    title: str | None = None
    reliability: float
    independence: float
    specificity: float
    freshness: float
    independence_group: str | None = None


class TrustCertificateSourceSummary(BaseModel):
    source_id: str
    domain: str | None = None
    reliability: float | None = None
    reliability_source: str | None = None
    independence_group: str | None = None


class TrustCertificateIndependenceSummary(BaseModel):
    cluster_id: str
    evidence_count: int
    average_independence: float
    average_corroboration_discount: float | None = None


class TrustCertificateLifecycleEvent(BaseModel):
    event_type: str
    event_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status_before: CertificateLifecycleStatus | None = None
    status_after: CertificateLifecycleStatus
    reason: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class TrustCertificate(BaseModel):
    certificate_id: str
    case_id: str
    lifecycle_status: CertificateLifecycleStatus = "draft"
    issued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None
    lifecycle_events: list[TrustCertificateLifecycleEvent] = Field(default_factory=list)

    overall_verdict: str
    confidence: float
    trust_index: float

    claims: list[TrustCertificateClaimSummary] = Field(default_factory=list)
    evidence: list[TrustCertificateEvidenceSummary] = Field(default_factory=list)
    sources: list[TrustCertificateSourceSummary] = Field(default_factory=list)
    independence_clusters: list[TrustCertificateIndependenceSummary] = Field(default_factory=list)

    evidence_graph_id: str | None = None
    evidence_graph_summary: dict[str, Any] = Field(default_factory=dict)

    summary: dict[str, Any] = Field(default_factory=dict)


class TrustCertificateRegistryItem(BaseModel):
    certificate_id: str
    case_id: str
    lifecycle_status: CertificateLifecycleStatus
    overall_verdict: str
    confidence: float
    trust_index: float
    issued_at: datetime
    updated_at: datetime | None = None
    claim_count: int = 0
    evidence_count: int = 0
    source_count: int = 0
    independence_cluster_count: int = 0
