from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from .common import APIModel, UTCDate

VerificationStatus = Literal["unverified", "verified", "rejected"]
FactType = Literal["medication", "lab"]


class FactSource(APIModel):
    source_type: Literal["document", "patient_answer"]
    source_id: str
    document_id: str | None = None
    extraction_id: str | None = None
    document_filename: str | None = None
    raw_text: str | None = None
    source_location: str | None = None


class MedicationValue(APIModel):
    name: str
    dosage: str | None = None
    unit: str | None = None
    route: str | None = None
    frequency: str | None = None
    duration: str | None = None
    start_date: UTCDate | None = None
    end_date: UTCDate | None = None
    instructions: str | None = None


class LabValue(APIModel):
    test_name: str
    value: str
    unit: str | None = None
    reference_range: str | None = None
    flag: str | None = None
    observation_timestamp: UTCDate | None = None


class FactRevision(APIModel):
    id: str
    version: int
    review_status: VerificationStatus
    corrected_data: dict | None = None
    reviewer_id: str
    review_notes: str | None = None
    reviewed_at: UTCDate


class MedicationFactRecord(APIModel):
    id: str
    fact_type: Literal["medication"] = "medication"
    original: MedicationValue
    current: MedicationValue
    source: FactSource
    verification_status: VerificationStatus
    review_version: int
    verified_by: str | None = None
    verified_at: UTCDate | None = None
    verification_notes: str | None = None
    revisions: list[FactRevision] = Field(default_factory=list)


class LabFactRecord(APIModel):
    id: str
    fact_type: Literal["lab"] = "lab"
    original: LabValue
    current: LabValue
    source: FactSource
    verification_status: VerificationStatus
    review_version: int
    verified_by: str | None = None
    verified_at: UTCDate | None = None
    verification_notes: str | None = None
    revisions: list[FactRevision] = Field(default_factory=list)


class FactStatusCounts(APIModel):
    unverified: int = 0
    verified: int = 0
    rejected: int = 0


class MedicalFactsResponse(APIModel):
    medications: list[MedicationFactRecord]
    labs: list[LabFactRecord]
    rejected_medications: list[MedicationFactRecord] = Field(default_factory=list)
    rejected_labs: list[LabFactRecord] = Field(default_factory=list)
    counts: FactStatusCounts


class MedicationCorrection(APIModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1)
    dosage: str | None = None
    unit: str | None = None
    route: str | None = None
    frequency: str | None = None
    duration: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    instructions: str | None = None

    @model_validator(mode="after")
    def require_field(self):
        if not self.model_fields_set:
            raise ValueError("At least one corrected medication field is required")
        return self


class LabCorrection(APIModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    test_name: str | None = Field(default=None, min_length=1)
    value: str | None = Field(default=None, min_length=1)
    unit: str | None = None
    reference_range: str | None = None
    flag: str | None = None
    observation_timestamp: datetime | None = None

    @model_validator(mode="after")
    def require_field(self):
        if not self.model_fields_set:
            raise ValueError("At least one corrected lab field is required")
        return self


class MedicationFactReview(APIModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    status: Literal["verified", "rejected"]
    correction: MedicationCorrection | None = None
    notes: str | None = Field(default=None, max_length=2000)


class LabFactReview(APIModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    status: Literal["verified", "rejected"]
    correction: LabCorrection | None = None
    notes: str | None = Field(default=None, max_length=2000)


class TimelineEntry(APIModel):
    id: str
    event_type: str
    canonical_label: str
    event_timestamp: UTCDate | None = None
    date_status: Literal["known", "partial", "unknown"]
    date_precision: Literal["datetime", "day", "month", "year", "unknown"]
    source: FactSource
    verification_status: VerificationStatus


class TimelineResponse(APIModel):
    known_date: list[TimelineEntry]
    unknown_date: list[TimelineEntry]


class DiscrepancySource(APIModel):
    source_type: Literal["patient_answer", "document_fact"]
    source_id: str
    label: str
    displayed_value: str
    document_id: str | None = None
    extraction_id: str | None = None
    raw_text: str | None = None


class Discrepancy(APIModel):
    discrepancy_id: str
    type: Literal[
        "MEDICATION_MISMATCH",
        "MEDICATION_MISSING_FROM_PATIENT_REPORT",
        "ALLERGY_CONFLICT",
        "LAB_VALUE_CONFLICT",
    ]
    workflow_priority: Literal["routine_review"] = "routine_review"
    source_a: DiscrepancySource
    source_b: DiscrepancySource
    reason: str
    status: Literal["open"] = "open"
    verification_state: Literal["requires_clinician_review"] = "requires_clinician_review"


class DiscrepancyResponse(APIModel):
    items: list[Discrepancy]
