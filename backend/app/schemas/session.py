from uuid import UUID

from pydantic import Field

from .adaptive import ClinicalHistory
from .alert import AlertItem
from .clinical_summary import ClinicalSummary
from .common import APIModel, Language, SessionStatus, UTCDate
from .consent import Consent
from .document import DocumentResponse
from .interview_answer import InterviewAnswer
from .patient import Patient, PatientCreate


class SessionCreate(APIModel):
    id: UUID
    patient: PatientCreate
    hospital_token: str = Field(min_length=1, max_length=80)
    language: Language


class Session(APIModel):
    id: str
    patient_id: str
    hospital_token: str
    language: Language
    status: SessionStatus
    started_at: UTCDate
    completed_at: UTCDate | None = None
    created_at: UTCDate
    updated_at: UTCDate | None = None
    user_id: str | None = None
    hospital_id: str | None = None
    selected_doctor_id: str | None = None


class SessionListItem(Session):
    patient_name: str
    queue_status: str | None = None
    queue_joined_at: UTCDate | None = None


class SessionList(APIModel):
    items: list[SessionListItem]


class SessionDetail(APIModel):
    session: Session
    patient: Patient
    consent: Consent | None
    answers: list[InterviewAnswer]
    summary: ClinicalSummary | None
    history: ClinicalHistory | None = None
    alerts: list[AlertItem] = Field(default_factory=list)
    documents: list[DocumentResponse] = Field(default_factory=list)


