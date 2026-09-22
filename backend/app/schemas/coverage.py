from typing import Literal

from pydantic import Field

from .common import APIModel

CoverageState = Literal[
    "CONFIRMED",
    "DOCUMENT_SUPPORTED_UNCONFIRMED",
    "CONFLICTED",
    "MISSING",
    "NOT_APPLICABLE",
]


class CoverageProvenance(APIModel):
    evidence_id: str
    source_fact_id: str
    source_document_id: str | None = None
    document_filename: str | None = None
    page_number: int | None = None
    bounding_box: dict | list | None = None
    ocr_provider: str | None = None
    ocr_model: str | None = None
    original_extracted_value: str | None = None
    verification_state: str


class CoverageField(APIModel):
    field: str
    label: str
    required: bool
    applicable: bool
    state: CoverageState
    patient_answer_id: str | None = None
    provenance: list[CoverageProvenance] = Field(default_factory=list)


class CoverageResponse(APIModel):
    session_id: str
    required: int
    confirmed: int
    document_supported_unconfirmed: int
    conflicted: int
    missing: int
    not_applicable: int
    fields: list[CoverageField]


class DocumentConfirmationContext(APIModel):
    question_source: Literal["DOCUMENT_CONFIRMATION"] = "DOCUMENT_CONFIRMATION"
    target_field: str
    evidence_id: str
    source_fact_id: str
    source_document_id: str | None = None
    document_filename: str | None = None
    page_number: int | None = None
    bounding_box: dict | list | None = None
    ocr_provider: str | None = None
    ocr_model: str | None = None
    original_extracted_value: str
    verification_state: str


class DocumentAwareDemoMetrics(APIModel):
    session_id: str
    questions_without_document_context: int = Field(ge=0)
    questions_with_document_context: int = Field(ge=0)
    questions_avoided: int = Field(ge=0)
    confirmation_questions_added: int = Field(ge=0)
