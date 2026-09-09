from app import models
from app.api.deps import DEMO_DOCTOR_ID
from app.core.config import demo_enabled
from app.database import SessionLocal


def main():
    if not demo_enabled():
        raise RuntimeError("Set DEMO_MODE=true in development before seeding.")
    with SessionLocal() as db:
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
    print("Demo doctor ready. No patient data was created.")


if __name__ == "__main__":
    main()
