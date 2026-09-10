import sys

from app import models
from app.api.deps import DEMO_DOCTOR_ID
from app.core.config import demo_enabled
from app.database import SessionLocal
from app.services.showcase import ShowcaseService


def main():
    if not demo_enabled():
        raise RuntimeError("Set DEMO_MODE=true in development before seeding.")

    with SessionLocal() as db:
        # Ensure demo doctor
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
