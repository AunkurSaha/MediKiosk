"""Frozen non-diagnostic clinical safety and evidence states.

Only deterministic, versioned rules may produce urgent or emergency routing
states. LLM, RAG, OCR, and normalization outputs are evidence inputs only and
must never override those rules or become verified clinical truth implicitly.
MediKiosk intentionally has no ``NO_DOCTOR_REQUIRED`` state.
"""

from enum import StrEnum


class CareRoutingState(StrEnum):
    EMERGENCY = "EMERGENCY"
    URGENT = "URGENT"
    ROUTINE_OPD = "ROUTINE_OPD"
    TELECONSULT_MAY_BE_SUITABLE = "TELECONSULT_MAY_BE_SUITABLE"


class EvidenceSourceType(StrEnum):
    PATIENT_TEXT = "PATIENT_TEXT"
    PATIENT_VOICE = "PATIENT_VOICE"
    DOCUMENT = "DOCUMENT"
    PREVIOUS_ENCOUNTER = "PREVIOUS_ENCOUNTER"
    CLINICIAN = "CLINICIAN"
    DETERMINISTIC_RULE = "DETERMINISTIC_RULE"
    EXTERNAL_RECORD = "EXTERNAL_RECORD"


class EvidenceVerificationStatus(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    PATIENT_CONFIRMED = "PATIENT_CONFIRMED"
    CLINICIAN_VERIFIED = "CLINICIAN_VERIFIED"
    REJECTED = "REJECTED"
    CONFLICTING = "CONFLICTING"


TRUSTED_HISTORY_STATUSES = frozenset(
    {
        EvidenceVerificationStatus.PATIENT_CONFIRMED,
        EvidenceVerificationStatus.CLINICIAN_VERIFIED,
    }
)
