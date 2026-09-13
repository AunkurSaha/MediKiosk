import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app import models
from app.api.deps import DEMO_DOCTOR_ID
from app.schemas.document import StructuredDocument
from app.services import adaptive, red_flags, storage
from app.services.clinical_summary import ClinicalSummaryService
from app.services.document_parser import parse_document
from app.services.medical_extractor import extract_medical_facts

SHOWCASE_TOKEN = "T-SHOWCASE-101"
SHOWCASE_PATIENT_NAME = "Sunita Sharma (সুমিতা শর্মা)"
FIXTURE_ROOT = Path(__file__).resolve().parents[3] / "ai" / "document_fixtures"


class ShowcaseService:
    @staticmethod
    def _answer_rows(session_id: str, created_at: datetime) -> list[models.InterviewAnswer]:
        # Values follow the pinned chest-pain flow exactly. Text is synthetic patient-reported
        # demo content; touch answers are stored as touch, never fabricated as voice input.
        answers = [
            (
                "chief_complaint.description",
                "বুকে তীব্র ব্যথা এবং চাপ লাগছে",
                "বুকে তীব্র ব্যথা এবং চাপ লাগছে",
                "typed",
            ),
            ("hpi.onset", {"amount": 1, "unit": "days"}, "গতকাল থেকে", "touch"),
            ("hpi.site", "বুকের মাঝখানে", "বুকের মাঝখানে", "typed"),
            ("hpi.character", "চাপের মতো", "চাপের মতো", "typed"),
            ("hpi.radiation", True, "হ্যাঁ", "touch"),
            ("hpi.radiation_site", "বাম হাতে", "বাম হাতে", "typed"),
            ("hpi.associated_details", "শ্বাসকষ্ট", "শ্বাসকষ্ট", "typed"),
            ("hpi.timing", "intermittent", "আসে আর যায়", "touch"),
            ("hpi.exacerbating", "হাঁটলে বাড়ে", "হাঁটলে বাড়ে", "typed"),
            ("hpi.relieving", "বিশ্রামে কমে", "বিশ্রামে কমে", "typed"),
            ("hpi.severity", 9, "9", "touch"),
            ("past_medical_history.diabetes", True, "হ্যাঁ", "touch"),
            (
                "past_medical_history.diabetes_duration",
                {"amount": 5, "unit": "years"},
                "৫ বছর",
                "touch",
            ),
            (
                "past_medical_history.diabetes_care",
                "Metformin 500mg twice daily",
                "Metformin 500mg twice daily",
                "typed",
            ),
            ("past_medical_history.other", True, "হ্যাঁ", "touch"),
            (
                "past_medical_history.details",
                "Hypertension for 8 years",
                "Hypertension for 8 years",
                "typed",
            ),
            ("past_surgical_history.any", False, "না", "touch"),
            ("medications.any", True, "হ্যাঁ", "touch"),
            (
                "medications.details",
                "Metformin 500mg twice daily, Atorvastatin 40mg daily, Metoprolol 50mg twice daily",
                "Metformin 500mg twice daily, Atorvastatin 40mg daily, Metoprolol 50mg twice daily",
                "typed",
            ),
            ("allergies.any", True, "হ্যাঁ", "touch"),
            (
                "allergies.details",
                "Penicillin allergy (skin rash)",
                "Penicillin allergy (skin rash)",
                "typed",
            ),
            ("family_history.any", False, "না", "touch"),
            ("personal_history.tobacco", "never", "কখনও ব্যবহার করিনি", "touch"),
            ("personal_history.alcohol", False, "না", "touch"),
            ("personal_history.context", "ঘুম কম হচ্ছে", "ঘুম কম হচ্ছে", "typed"),
            ("review_of_systems.other", False, "না", "touch"),
        ]
        return [
            models.InterviewAnswer(
                id=str(uuid.uuid4()),
                session_id=session_id,
                question_id=question_id,
                field=question_id,
                value_json=json.dumps(
                    {"status": "answered", "value": value}, ensure_ascii=False
                ),
                raw_value=raw_value,
                source=source,
                language="bn",
                verification_status="patient_reported",
                created_at=created_at + timedelta(seconds=index),
            )
            for index, (question_id, value, raw_value, source) in enumerate(answers)
        ]

    @classmethod
    def _seed_fixture_document(
        cls,
        db: DBSession,
        *,
        session_id: str,
        fixture_name: str,
        display_name: str,
        actor_user_id: str,
        created_at: datetime,
    ) -> str:
        fixture_path = FIXTURE_ROOT / fixture_name
        data = fixture_path.read_bytes()
        doc_id = str(uuid.uuid4())
        object_key, digest, size = storage.default_storage.save_file(
            session_id=session_id,
            doc_id=doc_id,
            filename=display_name,
            data=data,
        )

        catalog = json.loads((FIXTURE_ROOT / "catalog.json").read_text(encoding="utf-8"))
        fixture = catalog.get(digest)
        if fixture is None:
            raise RuntimeError(f"Showcase fixture {fixture_name} is absent from the OCR catalog.")
        raw_text = fixture["raw_text"]
        document_type, document_date, structured = parse_document(raw_text, display_name)
        structured_payload = StructuredDocument.model_validate(structured).model_dump(mode="json")

        document = models.Document(
            id=doc_id,
            session_id=session_id,
            object_key=object_key,
            original_filename=display_name,
            media_type="image/png",
            file_size_bytes=size,
            sha256_hash=digest,
            document_type=document_type,
            document_date=document_date,
            processing_status="mock_fixture",
            created_at=created_at,
        )
        db.add(document)
        db.flush()

        extraction = models.DocumentExtraction(
            id=str(uuid.uuid4()),
            document_id=doc_id,
            session_id=session_id,
            extractor="mock",
            extractor_version="explicit-fixture-2.0",
            raw_text=raw_text,
            structured_json=structured_payload,
            confidence=None,
            verification_status="verified",
            review_version=1,
            verified_by=actor_user_id,
            verified_at=created_at + timedelta(minutes=5),
            verification_notes="Pre-reviewed synthetic showcase fixture.",
            created_at=created_at + timedelta(minutes=1),
        )
        db.add(extraction)
        db.flush()
        extract_medical_facts(db, extraction)

        fact_type, fact_model = (
            ("medication", models.MedicationFact)
            if document_type == "prescription"
            else ("lab", models.LabFact)
        )
        facts = list(
            db.scalars(
                select(fact_model).where(fact_model.document_extraction_id == extraction.id)
            )
        )
        for fact in facts:
            fact.verification_status = "verified"
            fact.review_version = 1
            fact.verified_by = actor_user_id
            fact.verified_at = created_at + timedelta(minutes=5)
            fact.verification_notes = "Pre-reviewed synthetic showcase fixture."
            original_data = {
                column.name: getattr(fact, column.name)
                for column in fact.__table__.columns
                if column.name
                not in {
                    "id",
                    "session_id",
                    "document_extraction_id",
                    "verification_status",
                    "review_version",
                    "verified_by",
                    "verified_at",
                    "verification_notes",
                    "created_at",
                    "updated_at",
                }
            }
            db.add(
                models.MedicalFactRevision(
                    session_id=session_id,
                    fact_type=fact_type,
                    fact_id=fact.id,
                    version=1,
                    review_status="verified",
                    original_data=original_data,
                    corrected_data=None,
                    reviewer_id=actor_user_id,
                    review_notes="Pre-reviewed synthetic showcase fixture.",
                    reviewed_at=created_at + timedelta(minutes=5),
                )
            )

        db.add(
            models.AuditLog(
                actor_user_id=actor_user_id,
                actor_type="DOCTOR",
                action="document_extraction_verified",
                entity_type="session",
                entity_id=session_id,
                metadata_json={
                    "document_id": document.id,
                    "extraction_id": extraction.id,
                    "status": "verified",
                    "fixture_id": fixture["fixture_id"],
                },
                created_at=created_at + timedelta(minutes=5),
            )
        )
        return object_key

    @classmethod
    def seed_showcase_patient(
        cls,
        db: DBSession,
        actor_user_id: str = DEMO_DOCTOR_ID,
        patient_user_id: str | None = None,
    ) -> dict:
        now = datetime.now(timezone.utc)
        existing_session = db.scalar(
            select(models.Session).where(models.Session.hospital_token == SHOWCASE_TOKEN)
        )
        if existing_session:
            if patient_user_id and existing_session.user_id != patient_user_id:
                existing_session.user_id = patient_user_id
                db.commit()
            summary_id = db.scalar(
                select(models.ClinicalSummary.id).where(
                    models.ClinicalSummary.session_id == existing_session.id
                )
            )
            patient = db.get(models.Patient, existing_session.patient_id)
            return {
                "session_id": existing_session.id,
                "patient_name": patient.name if patient else SHOWCASE_PATIENT_NAME,
                "hospital_token": existing_session.hospital_token,
                "language": existing_session.language,
                "status": existing_session.status,
                "summary_id": summary_id,
                "message": "Showcase patient already exists.",
            }

        created_object_keys: list[str] = []
        try:
            patient_id = str(uuid.uuid4())
            patient = models.Patient(
                id=patient_id,
                name=SHOWCASE_PATIENT_NAME,
                demo_abha_id="patient@abdm",
                created_at=now - timedelta(hours=3),
            )
            db.add(patient)

            hospital = db.scalar(select(models.Hospital).where(models.Hospital.active.is_(True)))
            hospital_id = hospital.id if hospital else None

            valid_doctor_id = None
            if actor_user_id:
                doc_profile = db.scalar(
                    select(models.DoctorProfile).where(models.DoctorProfile.doctor_user_id == actor_user_id)
                )
                if doc_profile:
                    valid_doctor_id = actor_user_id

            session_id = str(uuid.uuid4())
            session = models.Session(
                id=session_id,
                patient_id=patient_id,
                hospital_id=hospital_id,
                selected_doctor_id=valid_doctor_id,
                hospital_token=SHOWCASE_TOKEN,
                language="bn",
                status="intake",
                user_id=patient_user_id,
                started_at=now - timedelta(hours=2),
                created_at=now - timedelta(hours=2),
            )
            db.add(session)
            db.flush()

            if hospital_id and valid_doctor_id:
                membership = db.scalar(
                    select(models.DoctorHospitalMembership).where(
                        models.DoctorHospitalMembership.doctor_id == actor_user_id,
                        models.DoctorHospitalMembership.hospital_id == hospital_id,
                    )
                )
                if not membership:
                    db.add(
                        models.DoctorHospitalMembership(
                            doctor_id=actor_user_id,
                            hospital_id=hospital_id,
                            active=True,
                        )
                    )
                queue_entry = db.scalar(
                    select(models.DoctorQueueEntry).where(
                        models.DoctorQueueEntry.session_id == session_id
                    )
                )
                if not queue_entry:
                    db.add(
                        models.DoctorQueueEntry(
                            session_id=session_id,
                            doctor_id=actor_user_id,
                            hospital_id=hospital_id,
                            status="WAITING",
                            priority="HIGH",
                            joined_at=now - timedelta(hours=1),
                        )
                    )

            db.add(
                models.Consent(
                    id=str(uuid.uuid4()),
                    session_id=session_id,
                    share_with_doctor=True,
                    voice_processing=True,
                    document_processing=True,
                    created_at=now - timedelta(hours=2),
                )
            )

            from app.services.flow_registry import registry

            flow = registry().get("chest_pain")
            if flow is None:
                raise RuntimeError("The pinned chest-pain flow is unavailable.")
            run = models.InterviewRun(
                session_id=session_id,
                flow_id=flow.flow_id,
                flow_version=flow.version,
                flow_snapshot=flow.model_dump(mode="json"),
                cursor=None,
                revision=0,
            )
            db.add(run)
            db.add_all(cls._answer_rows(session_id, now - timedelta(hours=1, minutes=45)))
            db.flush()

            interview_state = adaptive.engine_for(db, session_id, flow).state()
            if not interview_state.is_complete or interview_state.missing_required:
                raise RuntimeError("Showcase answers do not complete the pinned chest-pain flow.")
            run.revision = len(interview_state.active_answers)

            alerts = red_flags.evaluate_and_persist(
                db, session_id, flow.flow_id, interview_state.active_answers
            )
            if {alert.rule_id for alert in alerts} != {"RF-CHEST-001", "RF-CHEST-002"}:
                raise RuntimeError("Showcase safety facts do not produce the expected alerts.")

            created_object_keys.append(
                cls._seed_fixture_document(
                    db,
                    session_id=session_id,
                    fixture_name="prescription.png",
                    display_name="showcase_prescription.png",
                    actor_user_id=actor_user_id,
                    created_at=now - timedelta(days=60),
                )
            )
            created_object_keys.append(
                cls._seed_fixture_document(
                    db,
                    session_id=session_id,
                    fixture_name="lab_report.png",
                    display_name="showcase_lab_report.png",
                    actor_user_id=actor_user_id,
                    created_at=now - timedelta(days=15),
                )
            )

            db.add(
                models.ABDMRecord(
                    id=str(uuid.uuid4()),
                    session_id=session_id,
                    patient_id=patient_id,
                    abha_number="91-1234-5678-9012",
                    abha_address="patient@abdm",
                    abha_status="mock_verified",
                    care_context_reference=f"medikiosk_ctx_{session_id[:8]}",
                    care_context_display=(
                        f"MediKiosk OPD Consultation - Token {SHOWCASE_TOKEN}"
                    ),
                    care_context_status="linked",
                    care_context_linked_at=now - timedelta(hours=1),
                    his_dispatch_status="dispatched",
                    his_dispatch_receipt=json.dumps(
                        {
                            "receipt_id": "HIS-ACK-SHOWCASE-101",
                            "status": "DELIVERED",
                            "target_system": "Central Hospital OPD HIS",
                            "endpoint": "local-simulated-gateway",
                            "mode": "synthetic_showcase",
                        }
                    ),
                    his_dispatched_at=now - timedelta(minutes=55),
                    created_at=now - timedelta(hours=1),
                )
            )

            session.status = "ready_for_review"
            session.completed_at = now - timedelta(hours=1)
            db.flush()

            draft_text, structured = ClinicalSummaryService.generate_draft(
                db, session_id, draft_version=1
            )
            summary = models.ClinicalSummary(
                id=str(uuid.uuid4()),
                session_id=session_id,
                generated_text=draft_text,
                generated_structured_json=structured.model_dump_json(),
                reviewed_text=draft_text,
                draft_provider="deterministic",
                draft_version=1,
                status="generated",
                generated_at=now - timedelta(hours=1),
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
                    actor_user_id=None,
                    review_notes="Deterministic synthetic showcase draft.",
                    structured_snapshot=structured.model_dump(mode="json"),
                )
            )
            db.add(
                models.AuditLog(
                    actor_user_id=None,
                    actor_type="SYSTEM",
                    action="SHOWCASE_SEEDED",
                    entity_type="session",
                    entity_id=session_id,
                    metadata_json={
                        "token": SHOWCASE_TOKEN,
                        "language": "bn",
                        "scenario": "chest_pain",
                        "synthetic": True,
                    },
                )
            )
            db.commit()
        except BaseException:
            db.rollback()
            for object_key in created_object_keys:
                storage.default_storage.delete_file(object_key)
            raise

        return {
            "session_id": session_id,
            "patient_name": SHOWCASE_PATIENT_NAME,
            "hospital_token": SHOWCASE_TOKEN,
            "language": "bn",
            "status": "ready_for_review",
            "summary_id": summary.id,
            "message": "Canonical Bengali chest-pain showcase patient seeded successfully.",
        }

    @classmethod
    def reset_demo_data(cls, db: DBSession) -> dict:
        object_keys = list(db.scalars(select(models.Document.object_key)))

        # Database changes are atomic; filesystem cleanup follows the successful commit.
        db.query(models.FieldVerificationRevision).delete()
        db.query(models.FieldVerification).delete()
        db.query(models.ABDMRecord).delete()
        db.query(models.SummaryRevision).delete()
        db.query(models.ClinicalSummary).delete()
        db.query(models.MedicationFact).delete()
        db.query(models.LabFact).delete()
        db.query(models.TimelineFact).delete()
        db.query(models.MedicalFactRevision).delete()
        db.query(models.DocumentExtraction).delete()
        db.query(models.Document).delete()
        db.query(models.Alert).delete()
        db.query(models.NormalizationResult).delete()
        db.query(models.InterviewAnswer).delete()
        db.query(models.InterviewRequest).delete()
        db.query(models.InterviewRun).delete()
        db.query(models.Consent).delete()
        db.query(models.Session).delete()
        db.query(models.Patient).delete()
        db.query(models.AuditLog).delete()

        if db.get(models.User, DEMO_DOCTOR_ID) is None:
            db.add(
                models.User(
                    id=DEMO_DOCTOR_ID,
                    name="Demo Doctor",
                    email="demo@medikiosk.invalid",
                    role="doctor",
                    is_active=True,
                )
            )
        db.add(
            models.AuditLog(
                actor_user_id=DEMO_DOCTOR_ID,
                actor_type="SYSTEM",
                action="DEMO_DATA_RESET",
                entity_type="demo",
                entity_id="all_synthetic_patient_data",
                metadata_json={"document_count": len(object_keys)},
            )
        )
        db.commit()

        cleanup_failures = sum(
            not storage.default_storage.delete_file(object_key) for object_key in object_keys
        )
        success = cleanup_failures == 0
        message = "Demo data reset successfully. User accounts preserved."
        if cleanup_failures:
            message += f" {cleanup_failures} document file(s) could not be removed."
        return {"success": success, "message": message}
