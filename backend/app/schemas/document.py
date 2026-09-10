from datetime import datetime
from typing import Literal

from pydantic import AliasChoices, ConfigDict, Field

from .common import APIModel

DocumentType = Literal["prescription", "lab_report", "other"]
ProcessingStatus = Literal[
    "pending", "processing", "completed", "failed", "unavailable", "mock_fixture"
]
VerificationStatus = Literal["unverified", "verified", "rejected"]


class MedicationFact(APIModel):
    name: str
    dosage: str | None = None
    unit: str | None = None
    frequency: str | None = None
    route: str | None = None
    duration: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    instructions: str | None = None


class LabObservationFact(APIModel):
    test_name: str
    value: str
    unit: str | None = None
    reference_range: str | None = None
    flag: str | None = None  # "normal", "high", "low", "abnormal"
    observation_timestamp: datetime | None = None


class AllergyStatement(APIModel):
    statement: Literal["allergy", "no_known_allergies"]
    substance: str | None = None
    raw_text: str


class StructuredDocument(APIModel):
    document_type: DocumentType | None = None
    document_date: str | None = None
    doctor_header: str | None = None
    raw_excerpt: str | None = None
    medications: list[MedicationFact] = Field(default_factory=list)
    observations: list[LabObservationFact] = Field(
        default_factory=list, validation_alias=AliasChoices("observations", "lab_observations")
    )
    allergies: list[AllergyStatement] = Field(default_factory=list)


class DocumentExtractionResponse(APIModel):
    id: str
    document_id: str
    session_id: str
    extractor: str
    extractor_version: str
    raw_text: str | None = None
    structured_json: StructuredDocument
    confidence: float | None = None
    verification_status: VerificationStatus
    review_version: int = 0
    verified_by: str | None = None
    verified_at: datetime | None = None
    verification_notes: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class DocumentResponse(APIModel):
    id: str
    session_id: str
    object_key: str
    original_filename: str
    media_type: str
    file_size_bytes: int
    sha256_hash: str
    document_type: DocumentType
    document_date: datetime | None = None
    processing_status: ProcessingStatus
    created_at: datetime
    updated_at: datetime | None = None
    extractions: list[DocumentExtractionResponse] = Field(default_factory=list)


class DocumentListResponse(APIModel):
    documents: list[DocumentResponse]
    total: int


class ExtractionVerifyRequest(APIModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["verified", "rejected"]
    expected_status: VerificationStatus = "unverified"
    expected_version: int = Field(default=0, ge=0)
    notes: str | None = None
