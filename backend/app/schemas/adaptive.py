from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr

from .alert import AlertSummary
from .common import APIModel, Language, UTCDate
from .continuity import ContinuityReconfirmationContext
from .coverage import DocumentConfirmationContext
from .flow import Localized, Question, SectionID
from .normalization import Normalization


class Duration(APIModel):
    amount: StrictInt | StrictFloat = Field(ge=0, le=1000, allow_inf_nan=False)
    unit: Literal["minutes", "hours", "days", "weeks", "months", "years"]


AnswerValue = StrictBool | StrictStr | StrictInt | StrictFloat | list[StrictStr] | Duration | None
AnswerStatus = Literal["answered", "unknown", "not_reported", "skipped"]


class Submission(APIModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    request_id: UUID
    expected_revision: int = Field(ge=0)
    question_id: str = Field(min_length=1, max_length=120)
    status: AnswerStatus = "answered"
    value: AnswerValue = None
    raw_value: str = Field(min_length=1, max_length=4000)
    source: Literal["typed", "touch", "voice"]
    voice_candidate: str | None = Field(default=None, max_length=24000)
    language: Language


class Selection(APIModel):
    flow_id: str


class Navigation(APIModel):
    question_id: str
    expected_revision: int = Field(ge=0)


class FlowChoice(APIModel):
    flow_id: str
    version: str
    namespace: Literal["standard", "ayush_demo", "legacy", "other"]
    label: Localized


class Fact(APIModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    answer_id: str
    question_id: str
    field: str
    label: Localized
    status: AnswerStatus
    value: AnswerValue
    raw_value: str
    source: str
    language: Language
    verification_status: Literal["patient_reported"] = "patient_reported"
    recorded_at: UTCDate
    normalization: Normalization | None = None


class RAGSuggestion(APIModel):
    question: str
    reason: str
    source_chunk_ids: list[str]
    origin: str = "rag"
    candidate_id: str | None = None
    target_field: str | None = None
    target_domain: str | None = None
    similarity_score: float | None = None
    source_title: str | None = None
    source_section: str | None = None
    generation_provider: str | None = None
    generation_model: str | None = None
    generation_fallback_used: bool | None = None
    generation_latency_ms: int | None = None
    template_question: str | None = None
    display_language: str | None = None
    translated_question: str | None = None
    translation_provider: str | None = None
    translation_fallback_used: bool | None = None


class HistorySection(APIModel):
    section_id: SectionID
    label: Localized
    facts: list[Fact]


class ClinicalHistory(APIModel):
    schema_version: Literal[1] = 1
    flow_id: str
    flow_version: str
    namespace: Literal["standard", "ayush_demo", "legacy", "other"]
    selected_complaint: Localized
    selection_source: Literal["patient_selected", "legacy_intake"]
    sections: list[HistorySection]


class Progress(APIModel):
    addressed: int
    applicable: int
    position: int


class InterviewState(APIModel):
    selection_required: bool = False
    flows: list[FlowChoice] = Field(default_factory=list)
    flow_id: str | None = None
    flow_version: str | None = None
    namespace: Literal["standard", "ayush_demo", "legacy", "other"] | None = None
    revision: int = 0
    section: Localized | None = None
    question: Question | None = None
    current_answer: Fact | None = None
    previous_question_id: str | None = None
    active_answers: list[Fact] = Field(default_factory=list)
    inactive_question_ids: list[str] = Field(default_factory=list)
    missing_required: list[str] = Field(default_factory=list)
    covered_domains: list[str] = Field(default_factory=list)
    missing_required_domains: list[str] = Field(default_factory=list)
    missing_optional_domains: list[str] = Field(default_factory=list)
    progress: Progress = Progress(addressed=0, applicable=0, position=0)
    is_complete: bool = False
    history: ClinicalHistory | None = None
    rag_suggestions: list[RAGSuggestion] = Field(default_factory=list)
    red_flag_alert: AlertSummary | None = None
    document_confirmation: DocumentConfirmationContext | None = None
    continuity_reconfirmation: ContinuityReconfirmationContext | None = None
