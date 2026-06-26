from pydantic import BaseModel, Field

from app.core.constants import CaseStatus, InputType, VerdictLabel
from app.schemas.agent import AtomicClaim, EvidenceItem, PivotVerdict, StanceResult
from app.schemas.audit import AgentRun, AuditTrail, CostLog
from app.schemas.correction import ClaimCorrection


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
    report: InvestigationReport | None = None

    agent_runs: list[AgentRun] = Field(default_factory=list)
    cost_logs: list[CostLog] = Field(default_factory=list)


class AuditTrailResponse(AuditTrail):
    pass
