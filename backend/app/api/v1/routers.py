from fastapi import APIRouter

from . import (
    adaptive,
    auth,
    consents,
    continuity,
    doctor,
    doctor_matching,
    documents,
    evidence,
    hospitals,
    interview,
    locations,
    medical,
    mediroute,
    pre_arrival_packet,
    rag,
    rapid_routing,
    sessions,
    speech,
    triage,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(hospitals.router, prefix="/hospitals", tags=["hospitals"])
api_router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
api_router.include_router(consents.router, prefix="/sessions", tags=["consent"])
api_router.include_router(continuity.router, prefix="/sessions", tags=["continuity"])
api_router.include_router(interview.router, prefix="/sessions", tags=["interview"])
api_router.include_router(adaptive.router, prefix="/sessions", tags=["adaptive interview"])
api_router.include_router(speech.router, prefix="/sessions", tags=["speech"])
api_router.include_router(documents.router, prefix="/sessions", tags=["documents"])
api_router.include_router(evidence.router, prefix="/evidence", tags=["clinical evidence"])
api_router.include_router(rapid_routing.router, prefix="/sessions", tags=["rapid clinical routing"])
api_router.include_router(doctor.router, prefix="/doctor", tags=["doctor"])
api_router.include_router(medical.router, prefix="/doctor/sessions", tags=["doctor medical facts"])
api_router.include_router(triage.router, prefix="/triage", tags=["triage"])
api_router.include_router(triage.session_router, prefix="/sessions", tags=["triage"])
api_router.include_router(rag.router, prefix="/rag", tags=["rag"])
api_router.include_router(locations.router, prefix="/sessions", tags=["location"])
api_router.include_router(mediroute.router, prefix="/sessions", tags=["mediroute"])
api_router.include_router(doctor_matching.router, prefix="/sessions", tags=["doctor matching"])
api_router.include_router(
    pre_arrival_packet.router, prefix="/sessions", tags=["pre-arrival packet"]
)
api_router.include_router(pre_arrival_packet.handoff_router, prefix="/handoff", tags=["handoff"])
