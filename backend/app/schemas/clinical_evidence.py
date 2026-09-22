from typing import Any

from pydantic import ConfigDict, Field, model_validator

from app.domain.clinical_safety import (
    CareRoutingState,
    EvidenceSourceType,
    EvidenceVerificationStatus,
)

from .common import APIModel, UTCDate


class ClinicalEvidenceCreate(APIModel):
    patient_id: str
    session_id: str
    concept_code: str | None = Field(default=None, max_length=160)
    value: Any = None
    source_type: EvidenceSourceType
    source_id: str
    stable_key: str = Field(default="value", min_length=1, max_length=160)
    original_text: str | None = None
    normalized_text: str | None = None
    translated_text: str | None = None
    language: str | None = Field(default=None, max_length=16)
    confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    verification_status: EvidenceVerificationStatus = EvidenceVerificationStatus.UNVERIFIED
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClinicalEvidenceRead(APIModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    patient_id: str
    session_id: str
    concept_code: str | None
    value: Any = None
    source_type: EvidenceSourceType
    source_id: str
    stable_key: str
    original_text: str | None
    normalized_text: str | None
    translated_text: str | None
    language: str | None
    confidence: float | None
    verification_status: EvidenceVerificationStatus
    metadata: dict[str, Any]
    verified_by: str | None
    verified_at: UTCDate | None
    verification_reason: str | None
    created_at: UTCDate
    updated_at: UTCDate | None
    conflicts_with: list[str] = Field(default_factory=list)


class ClinicalEvidenceList(APIModel):
    items: list[ClinicalEvidenceRead]


class ClinicalEvidenceQuery(APIModel):
    concept_code: str | None = None
    source_type: EvidenceSourceType | None = None
    verification_status: EvidenceVerificationStatus | None = None


class EvidenceVerificationUpdate(APIModel):
    reason: str | None = Field(default=None, max_length=2000)


class EvidenceConflictCreate(APIModel):
    other_evidence_id: str
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def distinct_evidence(self):
        if not self.other_evidence_id.strip():
            raise ValueError("other evidence is required")
        return self


class EvidenceContext(APIModel):
    verified: list[ClinicalEvidenceRead]
    patient_confirmed: list[ClinicalEvidenceRead]
    unverified_documents: list[ClinicalEvidenceRead]
    deterministic_rules: list[ClinicalEvidenceRead]
    conflicting: list[ClinicalEvidenceRead]


__all__ = [
    "CareRoutingState",
    "ClinicalEvidenceCreate",
    "ClinicalEvidenceList",
    "ClinicalEvidenceQuery",
    "ClinicalEvidenceRead",
    "EvidenceConflictCreate",
    "EvidenceContext",
    "EvidenceSourceType",
    "EvidenceVerificationStatus",
    "EvidenceVerificationUpdate",
]
