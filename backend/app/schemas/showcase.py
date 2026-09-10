from .common import APIModel, Language


class ShowcaseSeedResponse(APIModel):
    session_id: str
    patient_name: str
    hospital_token: str
    language: Language
    status: str
    summary_id: str | None
    message: str


class DemoResetResponse(APIModel):
    success: bool
    message: str
