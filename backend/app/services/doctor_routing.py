import json
import uuid
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.core import security
from app.core.config import demo_enabled
from app.core.errors import WorkflowError
from app.schemas.routing import DoctorAssignment, DoctorMatch, DoctorMatches, PatientQueueEstimate
from app.services import intake

DEMO_HOSPITAL_A = "10000000-0000-4000-8000-000000000001"
DEMO_HOSPITAL_B = "10000000-0000-4000-8000-000000000002"
DEMO_HOSPITAL_C = "10000000-0000-4000-8000-000000000003"
DEMO_HOSPITAL_D = "10000000-0000-4000-8000-000000000004"
DEMO_HOSPITAL_E = "10000000-0000-4000-8000-000000000005"
DEMO_DOCTOR_A = "00000000-0000-4000-8000-000000000001"
DEMO_DOCTOR_B = "20000000-0000-4000-8000-000000000002"
DEMO_DOCTOR_C = "20000000-0000-4000-8000-000000000003"
DEMO_DOCTOR_D = "20000000-0000-4000-8000-000000000004"
DEMO_DOCTOR_E = "20000000-0000-4000-8000-000000000005"
DEMO_DOCTOR_F = "20000000-0000-4000-8000-000000000006"
DEMO_DOCTOR_G = "20000000-0000-4000-8000-000000000007"
DEMO_DOCTOR_H = "20000000-0000-4000-8000-000000000008"
DEMO_DOCTOR_I = "20000000-0000-4000-8000-000000000009"
DEMO_DOCTOR_J = "20000000-0000-4000-8000-000000000010"
DEMO_DOCTOR_K = "20000000-0000-4000-8000-000000000011"

DEMO_DOCTOR_PASSWORD = "Doctor@123"
DEMO_GENERIC_COMPLAINTS = (
    "Patient reports a mild cough for routine assessment.",
    "Patient reports a low-grade fever for routine assessment.",
    "Patient reports an intermittent mild headache for routine assessment.",
    "Patient reports mild abdominal discomfort for routine assessment.",
    "Patient reports mild chest discomfort for routine assessment.",
)
DEMO_PATIENT_PROFILES = (
    (
        "Symptoms began this morning.",
        "No regular medicines reported.",
        "No known allergies reported.",
        "No long-term conditions reported.",
    ),
    (
        "Symptoms began about two days ago.",
        "Reports taking metformin regularly.",
        "Reports a penicillin allergy.",
        "Reports a history of type 2 diabetes.",
    ),
    (
        "Symptoms have occurred intermittently for one week.",
        "Medication history is not known.",
        "Allergy history is not known.",
        "Past medical history is not known.",
    ),
    (
        "Symptoms began gradually three days ago.",
        "Reports using an inhaler as previously prescribed.",
        "No known medicine allergies reported.",
        "Reports a history of asthma.",
    ),
    (
        "Symptoms started suddenly about six hours ago.",
        "Reports taking amlodipine regularly.",
        "Reports an allergy to sulfa medicines.",
        "Reports a history of high blood pressure.",
    ),
    (
        "Symptoms have been present for about two weeks.",
        "Reports occasional antacid use.",
        "No known allergies reported.",
        "Reports previous acid reflux symptoms.",
    ),
    (
        "Symptoms returned yesterday after improving last week.",
        "Reports taking a daily thyroid medicine.",
        "Reports an allergy to ibuprofen.",
        "Reports a history of hypothyroidism.",
    ),
    (
        "Symptoms began after exertion earlier today.",
        "Reports low-dose aspirin on a previous clinician's advice.",
        "Allergy history was not provided.",
        "Reports a previous cardiac evaluation; details need verification.",
    ),
    (
        "Symptoms have worsened gradually over four days.",
        "Reports no current prescription medicines.",
        "Reports a dust allergy.",
        "Reports seasonal breathing problems.",
    ),
    (
        "Duration is uncertain; symptoms were first noticed this week.",
        "Medicine names could not be recalled.",
        "No known food allergies reported.",
        "Reports a previous hospital admission; reason is not known.",
    ),
)
DEMO_PATIENT_LANGUAGES = ("en", "bn", "hi")
DEMO_DOCTORS = (
    (
        DEMO_DOCTOR_A,
        "Dr. Ananya Sen",
        "+919876500001",
        "MD, Cardiology",
        DEMO_HOSPITAL_A,
        ("CARDIOLOGY",),
        2,
    ),
    (
        DEMO_DOCTOR_B,
        "Dr. Rahul Das",
        "+919876500011",
        "MD, Cardiology",
        DEMO_HOSPITAL_A,
        ("CARDIOLOGY",),
        5,
    ),
    (
        DEMO_DOCTOR_C,
        "Dr. Ishan Gupta",
        "+919876500012",
        "MD, General Medicine",
        DEMO_HOSPITAL_A,
        ("GENERAL_MEDICINE", "NEUROLOGY"),
        1,
    ),
    (
        DEMO_DOCTOR_E,
        "Dr. Nandini Bose",
        "+919876500013",
        "MD, Pulmonology",
        DEMO_HOSPITAL_A,
        ("PULMONOLOGY",),
        3,
    ),
    (
        DEMO_DOCTOR_F,
        "Dr. Arjun Mehta",
        "+919876500014",
        "MD, Gastroenterology",
        DEMO_HOSPITAL_A,
        ("GASTROENTEROLOGY", "AYUSH"),
        4,
    ),
    (
        DEMO_DOCTOR_D,
        "Dr. Mira Roy",
        "+919876500021",
        "MD, Dermatology",
        DEMO_HOSPITAL_B,
        ("DERMATOLOGY",),
        4,
    ),
    (
        DEMO_DOCTOR_G,
        "Dr. Kabir Khan",
        "+919876500022",
        "MD, General Medicine",
        DEMO_HOSPITAL_B,
        ("GENERAL_MEDICINE",),
        2,
    ),
    (
        DEMO_DOCTOR_H,
        "Dr. Priyanka Pal",
        "+919876500023",
        "DM, Neurology",
        DEMO_HOSPITAL_B,
        ("NEUROLOGY",),
        5,
    ),
    (
        DEMO_DOCTOR_I,
        "Dr. Sayan Ghosh",
        "+919876500024",
        "MD, Pulmonology",
        DEMO_HOSPITAL_B,
        ("PULMONOLOGY",),
        1,
    ),
    (
        DEMO_DOCTOR_J,
        "Dr. Leena Iyer",
        "+919876500025",
        "MD, General Medicine",
        DEMO_HOSPITAL_B,
        ("GASTROENTEROLOGY", "AYUSH"),
        3,
    ),
    (
        DEMO_DOCTOR_K,
        "Dr. Riya Mukherjee",
        "+919876500031",
        "MS, Orthopedics",
        DEMO_HOSPITAL_C,
        ("ORTHOPEDICS",),
        1,
    ),
)

DEMO_DOCTOR_DIRECTORY = {
    DEMO_DOCTOR_A: (["CHEST_PAIN"], 12, ["en", "bn"], "AVAILABLE"),
    DEMO_DOCTOR_B: (["CHEST_PAIN", "ARRHYTHMIA"], 20, ["en", "hi"], "BUSY"),
    DEMO_DOCTOR_C: (["FEVER", "HEADACHE"], 18, ["en", "hi"], "AVAILABLE"),
    DEMO_DOCTOR_D: (["SKIN_CONDITIONS"], 14, ["en", "bn"], "AVAILABLE"),
    DEMO_DOCTOR_E: (["RESPIRATORY_SYMPTOMS"], 11, ["en", "bn"], "AVAILABLE"),
    DEMO_DOCTOR_F: (["ABDOMINAL_PAIN"], 9, ["en", "hi"], "UNKNOWN"),
    DEMO_DOCTOR_G: (["FEVER", "HEADACHE"], 8, ["en", "bn"], "AVAILABLE"),
    DEMO_DOCTOR_H: (["HEADACHE"], 16, ["en", "hi"], "BUSY"),
    DEMO_DOCTOR_I: (["RESPIRATORY_SYMPTOMS"], 10, ["en", "bn"], "AVAILABLE"),
    DEMO_DOCTOR_J: (["ABDOMINAL_PAIN"], 7, ["en", "hi"], "OFF_DUTY"),
    DEMO_DOCTOR_K: (["MUSCULOSKELETAL", "INJURY"], 12, ["en", "bn", "hi"], "AVAILABLE"),
}

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


@lru_cache
def eta_policy() -> dict:
    path = Path(__file__).resolve().parents[3] / "ai" / "queue" / "eta_policy_v1.json"
    policy = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(policy, dict):
        raise RuntimeError("Invalid queue ETA policy configuration")
    return policy


def list_active_hospitals(db: Session) -> list[models.Hospital]:
    ensure_demo_routing_data(db)
    return list(
        db.scalars(
            select(models.Hospital)
            .where(models.Hospital.active.is_(True))
            .order_by(models.Hospital.name, models.Hospital.id)
        )
    )


def doctor_roster(db: Session, hospital_id: str) -> list[dict]:
    ensure_demo_routing_data(db)
    waiting = (
        select(
            models.DoctorQueueEntry.doctor_id,
            func.count(models.DoctorQueueEntry.id).label("waiting_count"),
        )
        .where(
            models.DoctorQueueEntry.hospital_id == hospital_id,
            models.DoctorQueueEntry.status == "WAITING",
        )
        .group_by(models.DoctorQueueEntry.doctor_id)
        .subquery()
    )
    rows = db.execute(
        select(
            models.DoctorProfile.doctor_user_id,
            models.DoctorProfile.display_name,
            func.coalesce(waiting.c.waiting_count, 0),
        )
        .join(
            models.DoctorHospitalMembership,
            models.DoctorHospitalMembership.doctor_id == models.DoctorProfile.doctor_user_id,
        )
        .outerjoin(waiting, waiting.c.doctor_id == models.DoctorProfile.doctor_user_id)
        .where(
            models.DoctorHospitalMembership.hospital_id == hospital_id,
            models.DoctorHospitalMembership.active.is_(True),
            models.DoctorProfile.active.is_(True),
        )
        .order_by(models.DoctorProfile.display_name)
    ).all()
    return [
        {"doctor_id": doctor_id, "name": name, "waiting_count": int(waiting_count)}
        for doctor_id, name, waiting_count in rows
    ]


def ensure_demo_routing_data(db: Session) -> None:
    """Idempotent synthetic fixtures for the local demonstration only."""
    if not demo_enabled():
        return
    bind = db.get_bind()
    if getattr(bind, "_medikiosk_demo_routing_ready", False):
        return
    # Demo hospitals for the MediRoute directory (facility directory)
    # We'll create 5 demo facilities with varied capabilities as per the instruction.
    hospitals = [
        # Facility A: General Medicine, Cardiology, Emergency, ICU, Imaging
        (
            DEMO_HOSPITAL_A,
            "DEMO-KOL-01",
            "MediKiosk City Hospital",
            "Central Kolkata",
            "Kolkata",
            22.5726,
            88.3639,
            "General Hospital",
            "GENERAL_MEDICINE,CARDIOLOGY,EMERGENCY,ICU,IMAGING",
            True,
            "OPEN",
            True,
            "demo_facilities_v1",
        ),
        # Facility B: General Medicine, Dermatology, no emergency
        (
            DEMO_HOSPITAL_B,
            "DEMO-KOL-02",
            "MediKiosk Lake Medical Centre",
            "South Kolkata",
            "Kolkata",
            22.5448,
            88.3426,
            "Specialty Hospital",
            "GENERAL_MEDICINE,DERMATOLOGY",
            False,
            "OPEN",
            True,
            "demo_facilities_v1",
        ),
        # Facility C: Orthopedics, Surgery, Imaging
        (
            DEMO_HOSPITAL_C,
            "DEMO-KOL-03",
            "MediKiosk Ortho & Surgery Center",
            "East Kolkata",
            "Kolkata",
            22.5932,
            88.4120,
            "Specialty Hospital",
            "ORTHOPEDICS,SURGERY,IMAGING",
            False,
            "OPEN",
            True,
            "demo_facilities_v1",
        ),
        # Facility D: Pulmonology, Emergency, ICU
        (
            DEMO_HOSPITAL_D,
            "DEMO-KOL-04",
            "MediKiosk Pulmonology & Critical Care",
            "West Kolkata",
            "Kolkata",
            22.5210,
            88.2980,
            "Specialty Hospital",
            "PULMONOLOGY,EMERGENCY,ICU",
            True,
            "OPEN",
            True,
            "demo_facilities_v1",
        ),
        # Facility E: General Medicine only
        (
            DEMO_HOSPITAL_E,
            "DEMO-KOL-05",
            "MediKiosk Community Health Clinic",
            "North Kolkata",
            "Kolkata",
            22.6050,
            88.3800,
            "Clinic",
            "GENERAL_MEDICINE",
            False,
            "OPEN",
            True,
            "demo_facilities_v1",
        ),
    ]
    for (
        hospital_id,
        code,
        name,
        address,
        city,
        latitude,
        longitude,
        facility_type,
        capabilities,
        emergency_available,
        opening_status,
        is_demo,
        directory_version,
    ) in hospitals:
        hospital = db.get(models.Hospital, hospital_id)
        if hospital is None:
            hospital = models.Hospital(
                id=hospital_id,
                code=code,
                name=name,
                address=address,
                city=city,
            )
            db.add(hospital)
        hospital.latitude = latitude
        hospital.longitude = longitude
        hospital.locality = city
        hospital.facility_type = facility_type
        hospital.capabilities_json = capabilities.split(",")
        hospital.emergency_available = emergency_available
        hospital.opening_status = opening_status
        hospital.is_demo = is_demo
        hospital.directory_version = directory_version
        hospital.active = True
        db.flush()
    password_hash: str | None = None
    for doctor_id, name, phone_number, qualification, hospital_id, specialties, _ in DEMO_DOCTORS:
        user = db.get(models.User, doctor_id)
        if user is None:
            user = models.User(
                id=doctor_id,
                name=name,
                email=f"{doctor_id.replace('-', '')}@demo.medikiosk.local",
                phone_number=phone_number,
                role="doctor",
                is_active=True,
            )
            db.add(user)
            db.flush()
        user.name = name
        user.phone_number = phone_number
        user.is_active = True
        if user.hashed_password is None:
            password_hash = password_hash or security.hash_password(DEMO_DOCTOR_PASSWORD)
            user.hashed_password = password_hash
        profile = db.get(models.DoctorProfile, doctor_id)
        if profile is None:
            profile = models.DoctorProfile(
                doctor_user_id=doctor_id,
                display_name=name,
                qualification=qualification,
                active=True,
                accepting_patients=True,
            )
            db.add(profile)
            db.flush()
        else:
            profile.display_name = name
            profile.qualification = qualification
            profile.active = True
            profile.accepting_patients = True
        expertise, experience, languages, availability = DEMO_DOCTOR_DIRECTORY[doctor_id]
        profile.department = specialties[0]
        profile.primary_specialty = specialties[0]
        profile.subspecialties_json = list(specialties[1:])
        profile.expertise_tags_json = expertise
        profile.years_of_experience = experience
        profile.languages_json = languages
        profile.consultation_types_json = ["IN_PERSON"]
        profile.availability_status = availability
        profile.directory_version = "demo_doctors_v1"
        profile.is_demo = True
        profile.metadata_json = {"synthetic": True}
        if (
            db.scalar(
                select(models.DoctorHospitalMembership.id).where(
                    models.DoctorHospitalMembership.doctor_id == doctor_id,
                    models.DoctorHospitalMembership.hospital_id == hospital_id,
                )
            )
            is None
        ):
            db.add(
                models.DoctorHospitalMembership(
                    id=f"dh-{doctor_id[-4:]}-{hospital_id[-4:]}",
                    doctor_id=doctor_id,
                    hospital_id=hospital_id,
                    active=True,
                )
            )
        for specialty in specialties:
            if (
                db.scalar(
                    select(models.DoctorSpecialtyMembership.id).where(
                        models.DoctorSpecialtyMembership.doctor_id == doctor_id,
                        models.DoctorSpecialtyMembership.specialty_code == specialty,
                    )
                )
                is None
            ):
                db.add(
                    models.DoctorSpecialtyMembership(
                        id=f"ds-{doctor_id[-4:]}-{specialty.lower()}",
                        doctor_id=doctor_id,
                        specialty_code=specialty,
                    )
                )
    db.flush()
    for doctor_id, _, _, _, hospital_id, _, count in DEMO_DOCTORS:
        for index in range(count):
            legacy_session_id = f"demo-queue-{doctor_id[-4:]}-{index}"
            legacy_visit = db.get(models.Session, legacy_session_id)
            if legacy_visit is not None:
                legacy_visit.status = "cancelled"
                legacy_queue = db.scalar(
                    select(models.DoctorQueueEntry).where(
                        models.DoctorQueueEntry.session_id == legacy_session_id
                    )
                )
                if legacy_queue is not None:
                    legacy_queue.status = "CANCELLED"

            session_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"medikiosk:demo-queue:{doctor_id}:{index}",
                )
            )
            patient_id = f"demo-queue-patient-{doctor_id[-4:]}-{index}"
            if db.get(models.Patient, patient_id) is None:
                db.add(
                    models.Patient(
                        id=patient_id, name=f"Synthetic Patient {doctor_id[-2:]}-{index + 1}"
                    )
                )
            visit = db.get(models.Session, session_id)
            if visit is None:
                visit = models.Session(
                    id=session_id,
                    patient_id=patient_id,
                    hospital_token=f"DEMO-Q-{doctor_id[-4:]}-{index + 1}",
                    language="en",
                    status="ready_for_review",
                    hospital_id=hospital_id,
                    selected_doctor_id=doctor_id,
                )
                db.add(visit)
                db.flush()
            else:
                visit.hospital_id = hospital_id
                visit.selected_doctor_id = doctor_id
            consent = db.scalar(
                select(models.Consent).where(models.Consent.session_id == session_id)
            )
            if consent is None:
                db.add(
                    models.Consent(
                        session_id=session_id,
                        share_with_doctor=True,
                        voice_processing=False,
                        document_processing=False,
                    )
                )
            else:
                consent.share_with_doctor = True
            if (
                db.scalar(
                    select(models.DoctorQueueEntry.id).where(
                        models.DoctorQueueEntry.session_id == session_id
                    )
                )
                is None
            ):
                db.add(
                    models.DoctorQueueEntry(
                        id=str(
                            uuid.uuid5(
                                uuid.NAMESPACE_URL,
                                f"medikiosk:demo-queue-entry:{doctor_id}:{index}",
                            )
                        ),
                        session_id=session_id,
                        doctor_id=doctor_id,
                        hospital_id=hospital_id,
                        status="WAITING",
                    )
                )
            _ensure_generic_patient_record(db, visit, doctor_id, index)
            # Keep remote demo setup resilient: one patient's fixture is an
            # independent, idempotent transaction rather than holding all 30
            # patients in a single long-lived transaction.
            db.commit()
    bind._medikiosk_demo_routing_ready = True


def _ensure_generic_patient_record(
    db: Session,
    visit: models.Session,
    doctor_id: str,
    patient_index: int,
) -> None:
    """Attach safe, patient-reported demo content to a synthetic queue visit."""
    fixture_index = int(doctor_id[-2:]) + patient_index
    complaint_index = fixture_index % len(DEMO_GENERIC_COMPLAINTS)
    onset, medications, allergies, past_history = DEMO_PATIENT_PROFILES[
        fixture_index % len(DEMO_PATIENT_PROFILES)
    ]
    visit.language = DEMO_PATIENT_LANGUAGES[fixture_index % len(DEMO_PATIENT_LANGUAGES)]
    answers = (
        ("chief_complaint", DEMO_GENERIC_COMPLAINTS[complaint_index]),
        ("onset_duration", onset),
        ("medications", medications),
        ("allergies", allergies),
        ("past_history", past_history),
    )
    for position, (field, raw_value) in enumerate(answers):
        existing = db.scalar(
            select(models.InterviewAnswer.id).where(
                models.InterviewAnswer.session_id == visit.id,
                models.InterviewAnswer.field == field,
            )
        )
        if existing is None:
            db.add(
                models.InterviewAnswer(
                    id=f"demo-answer-{doctor_id[-4:]}-{patient_index}-{position}",
                    session_id=visit.id,
                    question_id=field,
                    field=field,
                    value_json=json.dumps({"status": "answered", "value": raw_value}),
                    raw_value=raw_value,
                    source="patient_typed",
                    language=visit.language,
                    verification_status="patient_reported",
                )
            )
    db.flush()

    summary = db.scalar(
        select(models.ClinicalSummary).where(models.ClinicalSummary.session_id == visit.id)
    )
    if summary is not None:
        return

    from app.services.clinical_summary import ClinicalSummaryService

    draft_text, structured = ClinicalSummaryService.generate_draft(db, visit.id, draft_version=1)
    summary = models.ClinicalSummary(
        id=str(uuid.uuid4()),
        session_id=visit.id,
        generated_text=draft_text,
        generated_structured_json=structured.model_dump_json(),
        reviewed_text=draft_text,
        draft_provider="deterministic",
        draft_version=1,
        status="generated",
        generated_at=datetime.now(timezone.utc),
        version=1,
    )
    db.add(summary)
    db.flush()
    db.add(
        models.SummaryRevision(
            summary_id=summary.id,
            version=1,
            revision_type="initial_draft",
            actor_type="SYSTEM",
            reviewed_text=draft_text,
            review_notes="Deterministic synthetic queue-patient draft.",
            structured_snapshot=structured.model_dump(mode="json"),
        )
    )


def select_hospital(
    db: Session, session_id: str, hospital_id: str, user: models.User | None
) -> models.Session:
    session = intake.get_session(db, session_id)
    intake.verify_session_access(db, session, user)
    if user is not None and user.role != "patient":
        raise WorkflowError("FORBIDDEN", "Patient access is required.", 403)
    if session.status != "intake" or db.get(models.InterviewRun, session_id):
        raise WorkflowError(
            "HOSPITAL_SELECTION_LOCKED",
            "Hospital cannot be changed after complaint selection.",
            409,
        )
    hospital = db.get(models.Hospital, hospital_id)
    if hospital is None or not hospital.active:
        raise WorkflowError("HOSPITAL_UNAVAILABLE", "Select an active hospital.", 422)
    session.hospital_id = hospital.id
    intake.audit(
        db, "hospital_selected", session.id, user=user, metadata={"hospital_id": hospital.id}
    )
    db.commit()
    db.refresh(session)
    return session


def _eligible_rows(db: Session, hospital_id: str, specialty_codes: list[str]):
    waiting = (
        select(
            models.DoctorQueueEntry.doctor_id,
            models.DoctorQueueEntry.hospital_id,
            func.count(models.DoctorQueueEntry.id).label("waiting_count"),
        )
        .where(
            models.DoctorQueueEntry.status == "WAITING",
            models.DoctorQueueEntry.hospital_id == hospital_id,
        )
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
        .join(
            models.DoctorHospitalMembership,
            models.DoctorHospitalMembership.doctor_id == models.DoctorProfile.doctor_user_id,
        )
        .join(
            models.DoctorSpecialtyMembership,
            models.DoctorSpecialtyMembership.doctor_id == models.DoctorProfile.doctor_user_id,
        )
        .outerjoin(
            waiting,
            (waiting.c.doctor_id == models.DoctorProfile.doctor_user_id)
            & (waiting.c.hospital_id == hospital_id),
        )
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


def matches_for_session(db: Session, session_id: str, user: models.User | None) -> DoctorMatches:
    session = intake.get_session(db, session_id)
    intake.verify_session_access(db, session, user)
    if user is not None and user.role != "patient":
        raise WorkflowError("FORBIDDEN", "Patient access is required.", 403)
    if not session.hospital_id:
        raise WorkflowError("HOSPITAL_REQUIRED", "Choose a hospital before finding a doctor.", 409)
    run = db.get(models.InterviewRun, session_id)
    if not run:
        raise WorkflowError(
            "COMPLAINT_REQUIRED", "Choose a health concern before finding a doctor.", 409
        )
    route = specialty_routes().get(run.flow_id)
    if not route:
        raise WorkflowError(
            "ROUTING_UNAVAILABLE",
            "No clinical service route is configured for this health concern.",
            422,
        )
    codes = route["primary"]
    rows = _eligible_rows(db, session.hospital_id, codes)
    fallback_used = False
    if not rows and route.get("fallback"):
        codes = route["fallback"]
        rows = _eligible_rows(db, session.hospital_id, codes)
        fallback_used = True
    by_doctor: dict[str, dict] = {}
    for profile, specialty, waiting_count in rows:
        item = by_doctor.setdefault(
            profile.doctor_user_id,
            {"profile": profile, "specialties": [], "waiting_count": int(waiting_count)},
        )
        item["specialties"].append(specialty)
    ordered = sorted(
        by_doctor.values(),
        key=lambda item: (
            item["waiting_count"],
            item["profile"].display_name.casefold(),
            item["profile"].doctor_user_id,
        ),
    )
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


def select_doctor(
    db: Session, session_id: str, doctor_id: str, user: models.User | None
) -> DoctorAssignment:
    session = intake.get_session(db, session_id)
    intake.verify_session_access(db, session, user)
    if session.status != "intake":
        raise WorkflowError(
            "DOCTOR_SELECTION_LOCKED", "Doctor cannot be changed after intake submission.", 409
        )
    eligible = matches_for_session(db, session_id, user)
    if doctor_id not in {item.doctor_id for item in eligible.items}:
        raise WorkflowError(
            "DOCTOR_NOT_ELIGIBLE", "Choose an available doctor shown for this visit.", 422
        )
    session.selected_doctor_id = doctor_id
    intake.audit(
        db,
        "doctor_selected",
        session.id,
        user=user,
        metadata={"doctor_id": doctor_id, "hospital_id": session.hospital_id},
    )
    db.commit()
    return DoctorAssignment(
        session_id=session.id, hospital_id=session.hospital_id, doctor_id=doctor_id
    )


def _queue_specialty_prefix(db: Session, doctor_id: str) -> str:
    specialty = db.scalar(
        select(models.DoctorProfile.primary_specialty).where(
            models.DoctorProfile.doctor_user_id == doctor_id
        )
    )
    if not specialty:
        specialty = db.scalar(
            select(models.DoctorSpecialtyMembership.specialty_code)
            .where(models.DoctorSpecialtyMembership.doctor_id == doctor_id)
            .order_by(models.DoctorSpecialtyMembership.specialty_code)
        )
    if not specialty:
        raise WorkflowError("DOCTOR_SPECIALTY_REQUIRED", "Doctor specialty is required for queueing.", 409)
    return specialty[:3]


def _allocate_queue_sequence(
    db: Session, *, hospital_id: str, doctor_id: str, service_date: date
) -> int:
    highest_sequence = db.scalar(
        select(func.max(models.DoctorQueueEntry.sequence_number)).where(
            models.DoctorQueueEntry.hospital_id == hospital_id,
            models.DoctorQueueEntry.doctor_id == doctor_id,
            models.DoctorQueueEntry.service_date == service_date,
        )
    )
    return (highest_sequence or 0) + 1


def enqueue_completed_session(db: Session, session: models.Session) -> models.DoctorQueueEntry:
    if not session.hospital_id or not session.selected_doctor_id:
        raise WorkflowError("DOCTOR_REQUIRED", "Choose a doctor before submitting intake.", 409)
    entry = db.scalar(
        select(models.DoctorQueueEntry).where(models.DoctorQueueEntry.session_id == session.id)
    )
    if entry is None:
        service_date = datetime.now(timezone.utc).date()
        sequence_number = _allocate_queue_sequence(
            db,
            hospital_id=session.hospital_id,
            doctor_id=session.selected_doctor_id,
            service_date=service_date,
        )
        entry = models.DoctorQueueEntry(
            session_id=session.id,
            doctor_id=session.selected_doctor_id,
            hospital_id=session.hospital_id,
            patient_id=session.patient_id,
            service_date=service_date,
            sequence_number=sequence_number,
            visit_token=(
                f"MK-{_queue_specialty_prefix(db, session.selected_doctor_id)}-{sequence_number:03d}"
            ),
            status="WAITING",
            joined_at=datetime.now(timezone.utc),
        )
        db.add(entry)
    return entry


def patient_queue_estimate(
    db: Session, session_id: str, user: models.User | None
) -> PatientQueueEstimate:
    session = intake.get_session(db, session_id)
    intake.verify_session_access(db, session, user)
    entry = db.scalar(
        select(models.DoctorQueueEntry).where(models.DoctorQueueEntry.session_id == session.id)
    )
    if entry is None:
        raise WorkflowError(
            "QUEUE_ENTRY_NOT_FOUND", "No queue reservation exists for this visit.", 404
        )

    # REPLACED: Queue logic replaced with COUNT-based approach for proper FIFO handling
    # DIAGNOSTIC: Count all matching entries first
    total_matching = db.scalar(
        select(func.count(models.DoctorQueueEntry.id))
        .where(
            models.DoctorQueueEntry.doctor_id == entry.doctor_id,
            models.DoctorQueueEntry.hospital_id == entry.hospital_id,
            models.DoctorQueueEntry.service_date == entry.service_date,
            models.DoctorQueueEntry.status.in_(("WAITING", "CALLED")),
        )
    ) or 0
    if entry.sequence_number is None:
        fifo_ahead = models.DoctorQueueEntry.joined_at < entry.joined_at
    else:
        fifo_ahead = (models.DoctorQueueEntry.joined_at < entry.joined_at) | (
            (models.DoctorQueueEntry.joined_at == entry.joined_at)
            & (models.DoctorQueueEntry.sequence_number < entry.sequence_number)
        )

    # Apply FIFO ordering; legacy rows without a sequence use their joined timestamp only.
    patients_ahead = db.scalar(
        select(func.count(models.DoctorQueueEntry.id))
        .where(
            models.DoctorQueueEntry.doctor_id == entry.doctor_id,
            models.DoctorQueueEntry.hospital_id == entry.hospital_id,
            models.DoctorQueueEntry.service_date == entry.service_date,
            models.DoctorQueueEntry.status.in_(("WAITING", "CALLED")),
            fifo_ahead,
        )
    ) or 0
    # For debugging, we could return both values, but let's just use patients_ahead for now
    # In a real debug scenario, we might log or inspect these values
    doctor_name = db.scalar(select(models.User.name).where(models.User.id == entry.doctor_id))
    hospital_name = db.scalar(
        select(models.Hospital.name).where(models.Hospital.id == entry.hospital_id)
    )
    policy = eta_policy()
    position = patients_ahead + 1 if patients_ahead is not None else 1
    estimated_wait_minutes = patients_ahead * policy["default_consultation_minutes"]
    patient_word = "patient" if patients_ahead == 1 else "patients"
    return PatientQueueEstimate(
        session_id=session.id,
        doctor_id=entry.doctor_id,
        doctor_name=doctor_name or "your selected doctor",
        hospital_name=hospital_name or "your selected facility",
        position=position,
        patients_ahead=patients_ahead,
        status=entry.status,
        visit_token=entry.visit_token,
        hospital_id=entry.hospital_id,
        service_date=entry.service_date,
        estimated_wait_minutes=estimated_wait_minutes,
        is_estimate=True,
        calculation_basis=f"{patients_ahead} {patient_word} ahead × {policy['default_consultation_minutes']} min average consultation",
        policy_version=policy["version"],
    )


def require_assigned_doctor(db: Session, session: models.Session, user: models.User) -> None:
    if user.role != "doctor" or session.selected_doctor_id != user.id:
        raise WorkflowError("FORBIDDEN", "This intake is assigned to another doctor.", 403)
    active_membership = db.scalar(
        select(models.DoctorHospitalMembership.id).where(
            models.DoctorHospitalMembership.doctor_id == user.id,
            models.DoctorHospitalMembership.hospital_id == session.hospital_id,
            models.DoctorHospitalMembership.active.is_(True),
        )
    )
    if active_membership is None:
        raise WorkflowError("FORBIDDEN", "Active hospital membership is required.", 403)


def transition_queue(
    db: Session, session_id: str, status: str, user: models.User
) -> models.DoctorQueueEntry:
    session = intake.get_session(db, session_id)
    require_assigned_doctor(db, session, user)
    entry = db.scalar(
        select(models.DoctorQueueEntry).where(models.DoctorQueueEntry.session_id == session_id)
    )
    if entry is None:
        raise WorkflowError("QUEUE_ENTRY_NOT_FOUND", "Queue entry not found.", 404)
    if status not in ALLOWED_TRANSITIONS.get(entry.status, set()):
        raise WorkflowError(
            "INVALID_QUEUE_TRANSITION", "Queue status transition is not allowed.", 409
        )
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
