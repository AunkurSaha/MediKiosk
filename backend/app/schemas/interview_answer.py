from typing import Literal

from pydantic import ConfigDict, Field

from .adaptive import AnswerStatus, AnswerValue
from .common import APIModel, FieldName, Language, UTCDate


class InterviewAnswerCreate(APIModel):
    question_id: FieldName
    field: FieldName
    value: str = Field(min_length=1, max_length=4000)
    raw_value: str = Field(min_length=1, max_length=4000)
    source: Literal["touch", "typed", "voice"]
    language: Language


class InterviewAnswer(APIModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    id: str
    session_id: str
    question_id: str
    field: str
    value: AnswerValue
    status: AnswerStatus = "answered"
    raw_value: str | None = None
    source: str
    language: str
    verification_status: str
    created_at: UTCDate
    updated_at: UTCDate | None = None
