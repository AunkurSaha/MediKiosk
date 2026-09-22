"""Synthetic directory fixtures for the explicitly local E2E runtime only."""

from pathlib import Path

from sqlalchemy import select

from app import models
from app.core.config import APP_ENV
from app.database import SessionLocal
from app.seed import main as seed_demo
from app.services.doctor_routing import (
    DEMO_DOCTOR_A,
    DEMO_DOCTOR_B,
    DEMO_DOCTOR_D,
    DEMO_HOSPITAL_A,
)


def main() -> None:
    if APP_ENV != "e2e":
        raise RuntimeError("E2E seed is available only with APP_ENV=e2e.")
    seed_demo()
    fixture_root = Path(__file__).resolve().parents[2] / "ai" / "document_fixtures"
    required_fixtures = (
        "catalog.json",
        "metformin_prescription.png",
        "fasting_glucose_lab.png",
    )
    missing = [name for name in required_fixtures if not (fixture_root / name).is_file()]
    if missing:
        raise RuntimeError(f"Required local document fixtures are missing: {', '.join(missing)}")
    with SessionLocal() as db:
        for doctor_id, languages, availability in (
            (DEMO_DOCTOR_A, ["en", "bn"], "BUSY"),
            (DEMO_DOCTOR_B, ["en", "hi"], "AVAILABLE"),
        ):
            cardiologist = db.get(models.DoctorProfile, doctor_id)
            if cardiologist is None:
                raise RuntimeError("Demo cardiology directory was not seeded.")
            cardiologist.availability_status = availability
            cardiologist.years_of_experience = 12
            cardiologist.expertise_tags_json = ["CHEST_PAIN"]
            cardiologist.languages_json = languages
            cardiologist.directory_version = "e2e_doctors_v1"
        dermatologist = db.get(models.DoctorProfile, DEMO_DOCTOR_D)
        if dermatologist is None:
            raise RuntimeError("Demo doctor directory was not seeded.")
        dermatologist.department = "DERMATOLOGY"
        dermatologist.primary_specialty = "DERMATOLOGY"
        dermatologist.availability_status = "AVAILABLE"
        dermatologist.expertise_tags_json = ["SKIN_CONDITIONS"]
        dermatologist.directory_version = "e2e_doctors_v1"
        emergency_facility = db.get(models.Hospital, DEMO_HOSPITAL_A)
        if emergency_facility is None or not emergency_facility.emergency_available:
            raise RuntimeError("Demo emergency-capable facility was not seeded.")
        if (
            db.scalar(
                select(models.DoctorHospitalMembership.id).where(
                    models.DoctorHospitalMembership.doctor_id == DEMO_DOCTOR_D,
                    models.DoctorHospitalMembership.hospital_id == DEMO_HOSPITAL_A,
                )
            )
            is None
        ):
            db.add(
                models.DoctorHospitalMembership(
                    doctor_id=DEMO_DOCTOR_D,
                    hospital_id=DEMO_HOSPITAL_A,
                    active=True,
                )
            )
        db.commit()
    print(
        "Local E2E directory seeded: General Medicine, Cardiology, Dermatology, emergency facilities."
    )


if __name__ == "__main__":
    main()
