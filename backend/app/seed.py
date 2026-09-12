import sys

from app import models
from app.api.deps import DEMO_DOCTOR_ID, DEMO_TRIAGE_ID
from app.core import security
from app.core.config import demo_enabled
from app.database import SessionLocal
from app.services.showcase import ShowcaseService


def main():
    if not demo_enabled():
        raise RuntimeError("Set DEMO_MODE=true in development before seeding.")

    with SessionLocal() as db:
        # Ensure demo doctor
        doc = db.get(models.User, DEMO_DOCTOR_ID)
        doc_hash = security.hash_password("Doctor@123")
        if doc is None:
            doc = models.User(
                id=DEMO_DOCTOR_ID,
                name="Dr. A. Sharma (Cardiology)",
                email="doctor@medikiosk.invalid",
                phone_number="+919876500001",
                role="doctor",
                hashed_password=doc_hash,
                is_active=True,
            )
            db.add(doc)
        else:
            doc.phone_number = "+919876500001"
            doc.hashed_password = doc_hash
            doc.name = "Dr. A. Sharma (Cardiology)"
        db.commit()

        # Ensure demo triage staff
        triage = db.get(models.User, DEMO_TRIAGE_ID)
        triage_hash = security.hash_password("Triage@123")
        if triage is None:
            triage = models.User(
                id=DEMO_TRIAGE_ID,
                name="Sister Priya (OPD Triage)",
                email="triage@medikiosk.invalid",
                phone_number="+919876500002",
                role="triage",
                hashed_password=triage_hash,
                is_active=True,
            )
            db.add(triage)
        else:
            triage.phone_number = "+919876500002"
            triage.hashed_password = triage_hash
            triage.name = "Sister Priya (OPD Triage)"
        db.commit()

        if "--reset" in sys.argv:
            res = ShowcaseService.reset_demo_data(db)
            print("Demo reset complete:", res["message"])
            return

        if "--showcase" in sys.argv:
            res = ShowcaseService.seed_showcase_patient(db)
            print("Showcase seeded successfully:", res["message"])
            print(f"Token: {res['hospital_token']} | Session: {res['session_id']}")
            return

        print(
            "Demo doctor ready. Use --showcase to seed Bengali chest-pain showcase patient or --reset to reset data."
        )


if __name__ == "__main__":
    main()
