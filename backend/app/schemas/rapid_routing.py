from typing import Any, Literal

from pydantic import Field

from app.domain.clinical_safety import CareRoutingState

from .common import APIModel, Language, UTCDate
from .flow import Localized

ComplaintCategory = Literal[
    "CHEST_DISCOMFORT",
    "FEVER",
    "HEADACHE",
    "BREATHING_DIFFICULTY",
    "ABDOMINAL_PAIN",
    "COUGH",
    "SKIN_PROBLEM",
    "INJURY",
    "JOINT_PAIN",
    "OTHER",
]


class ComplaintInput(APIModel):
    original_text: str = Field(min_length=1, max_length=4000)
    language: Language
    source: Literal["card", "typed", "voice"]
    translated_text: str | None = Field(default=None, max_length=4000)
    voice_candidate: str | None = Field(default=None, max_length=24000)


class ComplaintMapping(APIModel):
    original_text: str
    translated_text: str | None = None
    language: Language
    source: Literal["card", "typed", "voice"]
    candidate_category: ComplaintCategory
    mapping_provider: str
    confidence: float | None = None
    patient_confirmed: bool = False


class ComplaintConfirmation(APIModel):
    category: ComplaintCategory
    confirmed: Literal[True]
    expected_revision: int = Field(ge=0)


class RapidQuestion(APIModel):
    question_id: str
    concept_code: str
    target_field: str
    prompt: Localized
    input_type: Literal["boolean", "severity", "single_choice", "number"]
    options: list[dict[str, Any]] = Field(default_factory=list)
    required_for_safety: bool
    required_for_routing: bool
    equivalent_fields: list[str] = Field(default_factory=list)
    version: str


class RapidAnswer(APIModel):
    question_id: str
    value: bool | int | float | str
    raw_value: str = Field(min_length=1, max_length=4000)
    source: Literal["typed", "touch", "voice"]
    language: Language
    expected_revision: int = Field(ge=0)
    voice_candidate: str | None = Field(default=None, max_length=24000)


class RapidRoutingResultRead(APIModel):
    id: str
    session_id: str
    chief_complaint: ComplaintCategory
    routing_state: CareRoutingState
    suggested_specialty: str
    triggered_red_flags: list[str]
    supporting_evidence_ids: list[str]
    questions_asked: list[str]
    questions_skipped: list[str]
    completed_at: UTCDate
    routing_protocol_version: str


class RapidRoutingState(APIModel):
    phase: Literal["chief_complaint", "confirm_complaint", "rapid_interview", "result"]
    revision: int = 0
    mapping: ComplaintMapping | None = None
    chief_complaint: ComplaintCategory | None = None
    question: RapidQuestion | None = None
    questions_asked: list[str] = Field(default_factory=list)
    questions_skipped: list[str] = Field(default_factory=list)
    result: RapidRoutingResultRead | None = None
