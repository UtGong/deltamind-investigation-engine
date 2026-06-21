from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.core.constants import CaseStatus, InputType


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CaseRecord(BaseModel):
    case_id: str
    input_type: InputType
    input_text: str
    title: str | None = None
    status: CaseStatus = CaseStatus.CREATED

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
