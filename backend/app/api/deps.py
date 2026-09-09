from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app import models
from app.core.config import demo_enabled
from app.core.errors import WorkflowError
from app.database import get_db

DEMO_DOCTOR_ID = "00000000-0000-4000-8000-000000000001"


def get_current_user(
    db: Session = Depends(get_db),
    x_demo_doctor: str | None = Header(default=None),
):
    if not demo_enabled() or x_demo_doctor != "true":
        raise WorkflowError("AUTH_REQUIRED", "A configured doctor identity is required.", 401)
    user = db.get(models.User, DEMO_DOCTOR_ID)
    if user is None:
        raise WorkflowError("DEMO_NOT_SEEDED", "Run the demo doctor seed command.", 503)
    if not user.is_active or user.role != "doctor":
        raise WorkflowError("FORBIDDEN", "Doctor access is required.", 403)
    return user
