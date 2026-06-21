import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.constants import ClaimType, VerdictLabel
from app.domain.cases.models import utc_now
from app.schemas.agent import EvidenceItem, StanceResult


def normalize_claim_text(text: str) -> str:
    normalized = text.strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)

    # Keep words, numbers, whitespace, percent signs, and score hyphens.
    # Drop sentence punctuation so "Team A won 3-1." matches "team a won 3-1".
    normalized = re.sub(r"[^\w\s%-]", "", normalized)

    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


class VerifiedClaimRecord(BaseModel):
    normalized_claim_text: str
    claim_text: str
    claim_type: ClaimType = ClaimType.UNKNOWN

    verdict: VerdictLabel
    confidence: float = Field(ge=0.0, le=1.0)

    support_score: float = 0.0
    contradiction_score: float = 0.0
    uncertainty_score: float = 0.0

    reason: str
    evidence_count: int = 0

    freshness_policy: str = "unknown"
    expires_at: datetime | None = None

    evidence_snapshot: list[EvidenceItem] = Field(default_factory=list)
    stance_snapshot: list[StanceResult] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    metadata: dict[str, Any] = Field(default_factory=dict)
