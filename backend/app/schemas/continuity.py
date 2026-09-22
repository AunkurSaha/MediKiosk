from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from .common import APIModel

ContinuityStatus = Literal[
    "NEW",
    "UNCHANGED",
    "CHANGED",
    "RESOLVED",
    "CONFLICTED",
    "HISTORICAL_ONLY",
    "UNKNOWN_CURRENT_STATUS",
]


class PriorEncounter(APIModel):
    session_id: str
    completed_at: datetime | None = None
    facility: dict[str, Any] | None = None
    doctor: dict[str, Any] | None = None
    chief_complaint: str | None = None
    routing_state: str | None = None
    suggested_specialty: str | None = None
    completion_state: str


class ContinuityEvidenceRef(APIModel):
    evidence_id: str
    source_session_id: str
    source_encounter_date: datetime | None = None
    source_type: str
    canonical_field: str
    concept: str | None = None
    value: Any = None
    verification_status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    verified_at: datetime | None = None


class ContinuityItem(APIModel):
    canonical_field: str
    concept: str | None = None
    historical_value: Any = None
    current_value: Any = None
    status: ContinuityStatus
    historical_evidence_refs: list[ContinuityEvidenceRef] = Field(default_factory=list)
    current_evidence_refs: list[ContinuityEvidenceRef] = Field(default_factory=list)
    source_session_id: str | None = None
    source_date: datetime | None = None


class ContinuityReconfirmationContext(APIModel):
    """Serializable historical reference attached to one adaptive turn."""

    question_source: Literal["CONTINUITY_RECONFIRMATION"] = "CONTINUITY_RECONFIRMATION"
    target_field: str
    evidence_id: str
    source_session_id: str
    historical_value: Any = None
    canonical_field: str
    concept: str | None = None


class ContinuityChangeSet(APIModel):
    new: list[ContinuityItem] = Field(default_factory=list)
    changed: list[ContinuityItem] = Field(default_factory=list)
    unchanged: list[ContinuityItem] = Field(default_factory=list)
    resolved: list[ContinuityItem] = Field(default_factory=list)
    conflicted: list[ContinuityItem] = Field(default_factory=list)
    historical_unconfirmed: list[ContinuityItem] = Field(default_factory=list)
    unknown_current_status: list[ContinuityItem] = Field(default_factory=list)


class ContinuitySnapshot(APIModel):
    current_session_id: str
    previous_session_id: str | None = None
    previous_visit: PriorEncounter | None = None
    historical_evidence: list[ContinuityEvidenceRef] = Field(default_factory=list)
    longitudinal_timeline: list[ContinuityEvidenceRef] = Field(default_factory=list)
    changes: ContinuityChangeSet
    requires_reconfirmation: list[ContinuityItem] = Field(default_factory=list)
