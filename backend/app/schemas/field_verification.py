from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FieldVerificationStatus = Literal["unverified", "verified", "flagged"]
FieldVerificationType = Literal["interview_answer", "summary_statement"]


class FieldVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_type: FieldVerificationType
    field_id: str = Field(..., min_length=1, max_length=128)
    status: FieldVerificationStatus
    notes: str | None = Field(default=None, max_length=1000)
    expected_version: int | None = Field(default=None, ge=1)


class FieldVerificationRevisionRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    version: int
    status: str
    actor_user_id: str | None
    notes: str | None
    created_at: datetime


class FieldVerificationRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    field_type: str
    field_id: str
    status: str
    verified_by: str | None
    verified_at: datetime | None
    notes: str | None
    version: int
    created_at: datetime
    updated_at: datetime | None
    revisions: list[FieldVerificationRevisionRecord] = Field(default_factory=list)


class FieldVerificationList(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[FieldVerificationRecord]
