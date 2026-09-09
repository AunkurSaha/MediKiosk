from datetime import datetime
from typing import Any, Literal

from pydantic import ConfigDict, Field

from .common import APIModel

DocumentType = Literal["prescription", "lab_report", "other"]
ProcessingStatus = Literal["pending", "processing", "completed", "failed"]
VerificationStatus = Literal["unverified", "verified", "rejected"]


class MedicationFact(APIModel):
    name: str
    dosage: str | None = None
    frequency: str | None = None
    route: str | None = None
    duration: str | None = None


class LabObservationFact(APIModel):
    test_name: str
    value: str
    unit: str | None = None
    reference_range: str | None = None
    flag: str | None = None  # "normal", "high", "low", "abnormal"


class DocumentExtractionResponse(APIModel):
    id: str
    document_id: str
    session_id: str
    extractor: str
    extractor_version: str
    raw_text: str | None = None
    structured_json: dict[str, Any]
    confidence: float | None = None
    verification_status: VerificationStatus
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
    verified_by: str = Field(min_length=1, max_length=120)
    notes: str | None = None
