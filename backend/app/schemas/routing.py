from datetime import date
from typing import Literal

from pydantic import Field

from .common import APIModel, UTCDate

SpecialtyCode = Literal[
    "GENERAL_MEDICINE",
    "CARDIOLOGY",
    "NEUROLOGY",
    "PULMONOLOGY",
    "GASTROENTEROLOGY",
    "DERMATOLOGY",
    "ORTHOPAEDICS",
    "ENT",
    "PAEDIATRICS",
    "GYNAECOLOGY",
    "AYUSH",
]
QueueStatus = Literal["WAITING", "CALLED", "IN_CONSULTATION", "COMPLETED", "CANCELLED"]


class HospitalPublic(APIModel):
    id: str
    name: str
    city: str | None = None
    address: str | None = None


class HospitalList(APIModel):
    items: list[HospitalPublic]


class DoctorRosterItem(APIModel):
    doctor_id: str
    name: str
    waiting_count: int = Field(ge=0)


class DoctorRoster(APIModel):
    items: list[DoctorRosterItem]


class HospitalSelection(APIModel):
    hospital_id: str = Field(min_length=1, max_length=80)


class DoctorSelection(APIModel):
    doctor_id: str = Field(min_length=1, max_length=80)


class DoctorMatch(APIModel):
    doctor_id: str
    name: str
    qualification: str | None = None
    specialties: list[SpecialtyCode]
    matched_specialty: SpecialtyCode
    waiting_count: int = Field(ge=0)
    recommended: bool
    fallback: bool = False


class DoctorMatches(APIModel):
    specialty_codes: list[SpecialtyCode]
    fallback_used: bool
    items: list[DoctorMatch]


class DoctorAssignment(APIModel):
    session_id: str
    hospital_id: str
    doctor_id: str


class QueueEntryResponse(APIModel):
    id: str
    session_id: str
    doctor_id: str
    hospital_id: str
    status: QueueStatus
    joined_at: UTCDate


class PatientQueueEstimate(APIModel):
    session_id: str
    doctor_id: str
    doctor_name: str
    hospital_id: str
    hospital_name: str
    service_date: date | None = None
    visit_token: str | None = None
    status: QueueStatus
    position: int | None = Field(default=None, ge=1)
    patients_ahead: int = Field(ge=0)
    estimated_wait_minutes: int = Field(ge=0)
    is_estimate: bool
    calculation_basis: str
    policy_version: str


class QueueTransition(APIModel):
    status: Literal["CALLED", "IN_CONSULTATION", "COMPLETED", "CANCELLED"]
