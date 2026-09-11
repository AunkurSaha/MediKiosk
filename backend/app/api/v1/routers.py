from fastapi import APIRouter

from . import (
    adaptive,
    auth,
    consents,
    doctor,
    documents,
    interview,
    medical,
    sessions,
    speech,
    triage,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
api_router.include_router(consents.router, prefix="/sessions", tags=["consent"])
api_router.include_router(interview.router, prefix="/sessions", tags=["interview"])
api_router.include_router(adaptive.router, prefix="/sessions", tags=["adaptive interview"])
api_router.include_router(speech.router, prefix="/sessions", tags=["speech"])
api_router.include_router(documents.router, prefix="/sessions", tags=["documents"])
api_router.include_router(doctor.router, prefix="/doctor", tags=["doctor"])
api_router.include_router(medical.router, prefix="/doctor/sessions", tags=["doctor medical facts"])
api_router.include_router(triage.router, prefix="/triage", tags=["triage"])
api_router.include_router(triage.session_router, prefix="/sessions", tags=["triage"])
