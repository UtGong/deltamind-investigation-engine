from pydantic import BaseModel, Field


class ClaimCorrectionChange(BaseModel):
    field: str
    original: str | None = None
    corrected: str | None = None


class ClaimCorrection(BaseModel):
    claim_id: str
    needs_correction: bool = False

    corrected_claim: str | None = None
    correction_type: str = "none"
    changed_fields: list[ClaimCorrectionChange] = Field(default_factory=list)

    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)
    rationale: str = ""
