from typing import Literal

from pydantic import Field

from .common import APIModel, UTCDate


class ClinicalSummaryUpdate(APIModel):
    reviewed_text: str = Field(min_length=1, max_length=64000)
    expected_version: int = Field(ge=1)


class SummaryConfirm(APIModel):
    expected_version: int = Field(ge=1)


class ClinicalSummary(APIModel):
    id: str
    session_id: str
    generated_text: str | None = None
    generated_structured_json: str | None = None
    reviewed_text: str | None = None
    status: Literal["generated", "reviewed", "confirmed"]
    version: int
    generated_at: UTCDate | None = None
    reviewed_by: str | None = None
    reviewed_at: UTCDate | None = None
    confirmed_by: str | None = None
    confirmed_at: UTCDate | None = None
    created_at: UTCDate
    updated_at: UTCDate | None = None
