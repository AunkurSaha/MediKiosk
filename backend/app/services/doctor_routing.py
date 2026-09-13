import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.core.config import demo_enabled
from app.core.errors import WorkflowError
from app.schemas.routing import DoctorAssignment, DoctorMatch, DoctorMatches
from app.services import intake

DEMO_HOSPITAL_A = "10000000-0000-4000-8000-000000000001"
DEMO_HOSPITAL_B = "10000000-0000-4000-8000-000000000002"
DEMO_DOCTOR_A = "00000000-0000-4000-8000-000000000001"
DEMO_DOCTOR_B = "20000000-0000-4000-8000-000000000002"
DEMO_DOCTOR_D = "20000000-0000-4000-8000-000000000004"
DEMO_DOCTOR_C = "20000000-0000-4000-8000-000000000003"

ACTIVE_QUEUE_STATUSES = {"WAITING", "CALLED", "IN_CONSULTATION"}
ALLOWED_TRANSITIONS = {
    "WAITING": {"CALLED", "IN_CONSULTATION", "CANCELLED"},
    "CALLED": {"IN_CONSULTATION", "CANCELLED"},
    "IN_CONSULTATION": {"COMPLETED", "CANCELLED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}


@lru_cache
def specialty_routes() -> dict[str, dict[str, list[str]]]:
    path = Path(__file__).resolve().parents[3] / "ai" / "routing" / "complaint_specialties.json"
    routes = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(routes, dict):
        raise RuntimeError("Invalid complaint-specialty routing configuration")
    return routes


def list_active_hospitals(db: Session) -> list[models.Hospital]:
    ensure_demo_routing_data(db)
    return list(db.scalars(select(models.Hospital).where(models.Hospital.active.is_(True)).order_by(models.Hospital.name, models.Hospital.id)))


def ensure_demo_routing_data(db: Session) -> None:
    """Idempotent synthetic fixtures for the local demonstration only."""
    if not demo_enabled():
        return
    if db.get(models.Hospital, DEMO_HOSPITAL_A) is None:
        db.add_all([
            models.Hospital(id=DEMO_HOSPITAL_A, code="DEMO-KOL-01", name="MediKiosk City Hospital", address="Central Kolkata", city="Kolkata", active=True),
            models.Hospital(id=DEMO_HOSPITAL_B, code="DEMO-KOL-02", name="MediKiosk Lake Medical Centre", address="South Kolkata", city="Kolkata", active=True),
        ])
        db.flush()
    doctors = [
        (DEMO_DOCTOR_A, "Dr. Ananya Sen", "MD, Cardiology", DEMO_HOSPITAL_A, ["CARDIOLOGY"]),
        (DEMO_DOCTOR_B, "Dr. Rahul Das", "MD, Cardiology", DEMO_HOSPITAL_A, ["CARDIOLOGY"]),
        (DEMO_DOCTOR_C, "Dr. Ishan Gupta", "MD, General Medicine", DEMO_HOSPITAL_A, ["GENERAL_MEDICINE", "NEUROLOGY", "PULMONOLOGY", "GASTROENTEROLOGY", "AYUSH"]),
        (DEMO_DOCTOR_D, "Dr. Mira Roy", "MD, Cardiology", DEMO_HOSPITAL_B, ["CARDIOLOGY"]),
    ]
    for doctor_id, name, qualification, hospital_id, specialties in doctors:
        user = db.get(models.User, doctor_id)
        if user is None:
            db.add(models.User(id=doctor_id, name=name, email=f"{doctor_id.replace('-', '')}@demo.medikiosk.local", role="doctor", is_active=True))
            db.flush()
        if db.get(models.DoctorProfile, doctor_id) is None:
            db.add(models.DoctorProfile(doctor_user_id=doctor_id, display_name=name, qualification=qualification, active=True, accepting_patients=True))
            db.flush()
        if db.scalar(select(models.DoctorHospitalMembership.id).where(models.DoctorHospitalMembership.doctor_id == doctor_id, models.DoctorHospitalMembership.hospital_id == hospital_id)) is None:
            db.add(models.DoctorHospitalMembership(id=f"dh-{doctor_id[-4:]}-{hospital_id[-4:]}", doctor_id=doctor_id, hospital_id=hospital_id, active=True))
        for specialty in specialties:
            if db.scalar(select(models.DoctorSpecialtyMembership.id).where(models.DoctorSpecialtyMembership.doctor_id == doctor_id, models.DoctorSpecialtyMembership.specialty_code == specialty)) is None:
                db.add(models.DoctorSpecialtyMembership(id=f"ds-{doctor_id[-4:]}-{specialty.lower()}", doctor_id=doctor_id, specialty_code=specialty))
    db.flush()
    for doctor_id, count in ((DEMO_DOCTOR_A, 2), (DEMO_DOCTOR_B, 5)):
        for index in range(count):
            session_id = f"demo-queue-{doctor_id[-4:]}-{index}"
            if db.get(models.Session, session_id) is not None:
                continue
            patient_id = f"demo-queue-patient-{doctor_id[-4:]}-{index}"
            db.add(models.Patient(id=patient_id, name=f"Synthetic Queue Patient {index + 1}"))
            db.add(models.Session(id=session_id, patient_id=patient_id, hospital_token=f"DEMO-Q-{doctor_id[-4:]}-{index}", language="en", status="ready_for_review", hospital_id=DEMO_HOSPITAL_A, selected_doctor_id=doctor_id))
            db.flush()
            db.add(models.DoctorQueueEntry(id=f"queue-{doctor_id[-4:]}-{index}", session_id=session_id, doctor_id=doctor_id, hospital_id=DEMO_HOSPITAL_A, status="WAITING"))
    db.commit()


def select_hospital(db: Session, session_id: str, hospital_id: str, user: models.User) -> models.Session:
    session = intake.get_session(db, session_id)
    intake.verify_session_access(db, session, user)
    if user.role != "patient":
        raise WorkflowError("FORBIDDEN", "Patient access is required.", 403)
    if session.status != "intake" or db.get(models.InterviewRun, session_id):
        raise WorkflowError("HOSPITAL_SELECTION_LOCKED", "Hospital cannot be changed after complaint selection.", 409)
    hospital = db.get(models.Hospital, hospital_id)
    if hospital is None or not hospital.active:
        raise WorkflowError("HOSPITAL_UNAVAILABLE", "Select an active hospital.", 422)
    session.hospital_id = hospital.id
    intake.audit(db, "hospital_selected", session.id, user=user, metadata={"hospital_id": hospital.id})
    db.commit()
    db.refresh(session)
    return session


def _eligible_rows(db: Session, hospital_id: str, specialty_codes: list[str]):
    waiting = (
        select(models.DoctorQueueEntry.doctor_id, models.DoctorQueueEntry.hospital_id, func.count(models.DoctorQueueEntry.id).label("waiting_count"))
        .where(models.DoctorQueueEntry.status == "WAITING", models.DoctorQueueEntry.hospital_id == hospital_id)
        .group_by(models.DoctorQueueEntry.doctor_id, models.DoctorQueueEntry.hospital_id)
        .subquery()
    )
    return db.execute(
        select(
            models.DoctorProfile,
            models.DoctorSpecialtyMembership.specialty_code,
            func.coalesce(waiting.c.waiting_count, 0),
        )
        .join(models.User, models.User.id == models.DoctorProfile.doctor_user_id)
        .join(models.DoctorHospitalMembership, models.DoctorHospitalMembership.doctor_id == models.DoctorProfile.doctor_user_id)
        .join(models.DoctorSpecialtyMembership, models.DoctorSpecialtyMembership.doctor_id == models.DoctorProfile.doctor_user_id)
        .outerjoin(waiting, (waiting.c.doctor_id == models.DoctorProfile.doctor_user_id) & (waiting.c.hospital_id == hospital_id))
        .where(
            models.User.role == "doctor",
            models.User.is_active.is_(True),
            models.DoctorProfile.active.is_(True),
            models.DoctorProfile.accepting_patients.is_(True),
            models.DoctorHospitalMembership.hospital_id == hospital_id,
            models.DoctorHospitalMembership.active.is_(True),
            models.DoctorSpecialtyMembership.specialty_code.in_(specialty_codes),
        )
    ).all()


def matches_for_session(db: Session, session_id: str, user: models.User) -> DoctorMatches:
    session = intake.get_session(db, session_id)
    intake.verify_session_access(db, session, user)
    if user.role != "patient":
        raise WorkflowError("FORBIDDEN", "Patient access is required.", 403)
    if not session.hospital_id:
        raise WorkflowError("HOSPITAL_REQUIRED", "Choose a hospital before finding a doctor.", 409)
    run = db.get(models.InterviewRun, session_id)
    if not run:
        raise WorkflowError("COMPLAINT_REQUIRED", "Choose a health concern before finding a doctor.", 409)
    route = specialty_routes().get(run.flow_id)
    if not route:
        raise WorkflowError("ROUTING_UNAVAILABLE", "No clinical service route is configured for this health concern.", 422)
    codes = route["primary"]
    rows = _eligible_rows(db, session.hospital_id, codes)
    fallback_used = False
    if not rows and route.get("fallback"):
        codes = route["fallback"]
        rows = _eligible_rows(db, session.hospital_id, codes)
        fallback_used = True
    by_doctor: dict[str, dict] = {}
    for profile, specialty, waiting_count in rows:
        item = by_doctor.setdefault(profile.doctor_user_id, {"profile": profile, "specialties": [], "waiting_count": int(waiting_count)})
        item["specialties"].append(specialty)
    ordered = sorted(by_doctor.values(), key=lambda item: (item["waiting_count"], item["profile"].display_name.casefold(), item["profile"].doctor_user_id))
    items = [
        DoctorMatch(
            doctor_id=item["profile"].doctor_user_id,
            name=item["profile"].display_name,
            qualification=item["profile"].qualification,
            specialties=sorted(set(item["specialties"])),
            matched_specialty=sorted(set(item["specialties"]))[0],
            waiting_count=item["waiting_count"],
            recommended=index == 0,
            fallback=fallback_used,
        )
        for index, item in enumerate(ordered)
    ]
    return DoctorMatches(specialty_codes=codes, fallback_used=fallback_used, items=items)


def select_doctor(db: Session, session_id: str, doctor_id: str, user: models.User) -> DoctorAssignment:
    session = intake.get_session(db, session_id)
    intake.verify_session_access(db, session, user)
    if session.status != "intake":
        raise WorkflowError("DOCTOR_SELECTION_LOCKED", "Doctor cannot be changed after intake submission.", 409)
    eligible = matches_for_session(db, session_id, user)
    if doctor_id not in {item.doctor_id for item in eligible.items}:
        raise WorkflowError("DOCTOR_NOT_ELIGIBLE", "Choose an available doctor shown for this visit.", 422)
    session.selected_doctor_id = doctor_id
    intake.audit(db, "doctor_selected", session.id, user=user, metadata={"doctor_id": doctor_id, "hospital_id": session.hospital_id})
    db.commit()
    return DoctorAssignment(session_id=session.id, hospital_id=session.hospital_id, doctor_id=doctor_id)


def enqueue_completed_session(db: Session, session: models.Session) -> models.DoctorQueueEntry:
    if not session.hospital_id or not session.selected_doctor_id:
        raise WorkflowError("DOCTOR_REQUIRED", "Choose a doctor before submitting intake.", 409)
    entry = db.scalar(select(models.DoctorQueueEntry).where(models.DoctorQueueEntry.session_id == session.id))
    if entry is None:
        entry = models.DoctorQueueEntry(session_id=session.id, doctor_id=session.selected_doctor_id, hospital_id=session.hospital_id, status="WAITING")
        db.add(entry)
    return entry


def require_assigned_doctor(db: Session, session: models.Session, user: models.User) -> None:
    if user.role != "doctor" or session.selected_doctor_id != user.id:
        raise WorkflowError("FORBIDDEN", "This intake is assigned to another doctor.", 403)
    active_membership = db.scalar(select(models.DoctorHospitalMembership.id).where(models.DoctorHospitalMembership.doctor_id == user.id, models.DoctorHospitalMembership.hospital_id == session.hospital_id, models.DoctorHospitalMembership.active.is_(True)))
    if active_membership is None:
        raise WorkflowError("FORBIDDEN", "Active hospital membership is required.", 403)


def transition_queue(db: Session, session_id: str, status: str, user: models.User) -> models.DoctorQueueEntry:
    session = intake.get_session(db, session_id)
    require_assigned_doctor(db, session, user)
    entry = db.scalar(select(models.DoctorQueueEntry).where(models.DoctorQueueEntry.session_id == session_id))
    if entry is None:
        raise WorkflowError("QUEUE_ENTRY_NOT_FOUND", "Queue entry not found.", 404)
    if status not in ALLOWED_TRANSITIONS.get(entry.status, set()):
        raise WorkflowError("INVALID_QUEUE_TRANSITION", "Queue status transition is not allowed.", 409)
    now = datetime.now(timezone.utc)
    entry.status = status
    if status == "CALLED":
        entry.called_at = now
    elif status == "IN_CONSULTATION":
        entry.consultation_started_at = now
    elif status == "COMPLETED":
        entry.completed_at = now
    elif status == "CANCELLED":
        entry.cancelled_at = now
    intake.audit(db, "queue_status_changed", session_id, user=user, metadata={"status": status})
    db.commit()
    db.refresh(entry)
    return entry
