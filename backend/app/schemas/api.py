from typing import Any
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import CaseStatus, InputType, VerdictLabel
from app.schemas.agent import AtomicClaim, EvidenceItem, PivotVerdict, StanceResult
from app.schemas.audit import AgentRun, AuditTrail, CostLog
from app.schemas.correction import ClaimCorrection
from app.schemas.evidence_graph import EvidenceGraph
from app.schemas.trust_certificate import TrustCertificate


class CreateCaseRequest(BaseModel):
    input_type: InputType = InputType.CLAIM
    input_text: str = Field(min_length=1)
    title: str | None = None


class CaseResponse(BaseModel):
    case_id: str
    title: str | None = None
    input_type: InputType
    input_text: str
    status: CaseStatus
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AsyncInvestigationResponse(BaseModel):
    case_id: str
    status: CaseStatus
    message: str


class ClaimFinding(BaseModel):
    claim_id: str
    claim_text: str
    verdict: VerdictLabel
    confidence: float
    reason: str


class InvestigationReport(BaseModel):
    title: str
    verdict: VerdictLabel | None = None
    confidence: float | None = None

    summary: str
    claim_findings: list[ClaimFinding]
    key_evidence: list[str]
    remaining_uncertainty: list[str]
    memo_markdown: str


class InvestigationResult(BaseModel):
    case_id: str
    status: CaseStatus
    case_verdict: VerdictLabel | None = None
    confidence: float | None = None

    claims: list[AtomicClaim]
    evidence: list[EvidenceItem]
    stances: list[StanceResult]
    verdicts: list[PivotVerdict]
    corrections: list[ClaimCorrection] = Field(default_factory=list)
    evidence_graph: EvidenceGraph | None = None
    trust_certificate: TrustCertificate | None = None
    report: InvestigationReport | None = None

    agent_runs: list[AgentRun] = Field(default_factory=list)
    cost_logs: list[CostLog] = Field(default_factory=list)


class VerificationError(BaseModel):
    message: str
    case_id: str
    stage: str | None = None
    agent_name: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    upstream_status: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VerificationStateResponse(BaseModel):
    case_id: str
    case_available: bool
    case_status: str
    investigation_available: bool
    certificate_available: bool
    evidence_graph_available: bool
    error_available: bool
    case: CaseResponse
    investigation: InvestigationResult | None = None
    trust_certificate: TrustCertificate | None = None
    evidence_graph: EvidenceGraph | None = None
    error: VerificationError | None = None


class AuditTrailResponse(AuditTrail):
    pass
