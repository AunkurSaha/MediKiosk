from typing import Any, Literal

from pydantic import Field

from .common import APIModel, UTCDate
from .coverage import CoverageResponse


class EvidenceReference(APIModel):
    statement_id: str
    section: str
    statement_text: str
    source_type: Literal[
        "patient_answer",
        "normalized_fact",
        "medical_fact",
        "document",
        "alert",
        "discrepancy",
        "timeline",
    ]
    source_id: str
    source_text: str
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    status: Literal[
        "patient_reported",
        "patient_confirmed",
        "clinician_verified",
        "document_unverified",
        "conflicting",
        "normalized_unverified",
        "safety_rule",
        "timeline",
        "not_reported",
    ] = "patient_reported"
    badge: str = "Patient"
    evidence_refs: list[str] = Field(default_factory=list)
    source_summary: list[str] = Field(default_factory=list)
    provenance_explanation: list[str] = Field(default_factory=list)


class StructuredSummarySection(APIModel):
    section_key: str
    title: str
    content_lines: list[str] = Field(default_factory=list)
    items: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)


class StructuredClinicalSummary(APIModel):
    session_id: str
    generated_at: UTCDate
    draft_version: int
    draft_provider: str
    sections: list[StructuredSummarySection] = Field(default_factory=list)
    evidence_references: list[EvidenceReference] = Field(default_factory=list)
    disclaimer: str | None = None
    coverage: CoverageResponse | None = None


class PreArrivalPacket(APIModel):
    """Read-only doctor packet. The opaque reference contains no clinical data."""

    packet_reference: str
    visit_context: dict[str, Any] = Field(default_factory=dict)
    facility: dict[str, Any] | None = None
    selected_doctor: dict[str, Any] | None = None
    queue: dict[str, Any] | None = None
    routing: dict[str, Any] | None = None
    chief_complaint: str | None = None
    structured_history: list[dict[str, Any]] = Field(default_factory=list)
    documents: list[dict[str, Any]] = Field(default_factory=list)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    red_flags: list[dict[str, Any]] = Field(default_factory=list)
    coverage: CoverageResponse | None = None
    clinical_summary_id: str
    clinical_summary_status: str
    clinical_summary: StructuredClinicalSummary | None = None
    conflicts: list[dict[str, Any]] = Field(default_factory=list)


class ClinicalSummaryUpdate(APIModel):
    reviewed_text: str = Field(min_length=1, max_length=64000)
    expected_version: int = Field(ge=1)
    review_notes: str | None = Field(default=None, max_length=1000)


class SummaryConfirm(APIModel):
    expected_version: int = Field(ge=1)
    review_notes: str | None = Field(default=None, max_length=1000)


class SummaryRegenerateRequest(APIModel):
    expected_version: int = Field(ge=1)
    review_notes: str | None = Field(default=None, max_length=1000)
    confirm_replacement: bool = Field(default=False)


class SummaryRevisionRecord(APIModel):
    id: str
    summary_id: str
    version: int
    revision_type: Literal["initial_draft", "edit", "regenerate", "confirmed", "amendment"]
    actor_type: Literal["SYSTEM", "DOCTOR"]
    actor_user_id: str | None = None
    actor_name: str | None = None
    reviewed_text: str
    review_notes: str | None = None
    structured_snapshot: dict[str, Any] | None = None
    created_at: UTCDate


class SummaryAmendRequest(APIModel):
    amended_text: str = Field(..., min_length=1)
    amendment_notes: str = Field(..., min_length=3, max_length=2000)


class ClinicalSummary(APIModel):
    id: str
    session_id: str
    generated_text: str | None = None
    generated_structured_json: str | None = None
    reviewed_text: str | None = None
    confirmed_text: str | None = None
    amended_text: str | None = None
    amended_by: str | None = None
    amended_at: UTCDate | None = None
    amendment_notes: str | None = None
    status: Literal["generated", "reviewed", "confirmed", "amended"]
    draft_provider: str = "deterministic"
    draft_version: int = 1
    version: int
    generated_at: UTCDate | None = None
    reviewed_by: str | None = None
    reviewed_at: UTCDate | None = None
    confirmed_by: str | None = None
    confirmed_at: UTCDate | None = None
    created_at: UTCDate
    updated_at: UTCDate | None = None
    structured_summary: StructuredClinicalSummary | None = None
    evidence: list[EvidenceReference] | None = None
    coverage: CoverageResponse | None = None
    pre_arrival_packet: PreArrivalPacket | None = None
