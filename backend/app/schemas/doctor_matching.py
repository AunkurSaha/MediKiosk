from typing import Literal

from .common import APIModel, UTCDate


class DoctorRecommendation(APIModel):
    doctor_id: str
    name: str
    qualification: str | None
    primary_specialty: str
    expertise_tags: list[str]
    languages: list[str]
    availability_status: str
    years_of_experience: int
    rank: int
    recommended: bool
    eligibility_reasons: list[str]
    ranking_reasons: list[str]


class DoctorMatchResponse(APIModel):
    id: str
    session_id: str
    facility_id: str
    required_specialty: str
    directory_version: str
    protocol_version: str
    status: Literal["COMPLETED", "NO_ELIGIBLE_DOCTOR", "DOCTOR_MATCHING_BYPASSED_EMERGENCY"]
    selected_doctor_id: str | None
    generated_at: UTCDate
    recommendations: list[DoctorRecommendation]


class DoctorMatchSelection(APIModel):
    doctor_id: str
