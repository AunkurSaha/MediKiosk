from uuid import UUID

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app import models
from app.core.config import demo_enabled
from app.core.errors import WorkflowError
from app.database import get_db

DEMO_DOCTOR_ID = "00000000-0000-4000-8000-000000000001"
DEMO_TRIAGE_ID = "00000000-0000-4000-8000-000000000002"
SESSION_COOKIE_NAME = "medikiosk_session"


def extract_token(request: Request) -> str | None:
    """Extract session token from Authorization header or cookie."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        return token
    return None


def get_optional_auth_user(
    request: Request,
    db: Session = Depends(get_db),
    x_demo_doctor: str | None = Header(default=None),
    x_demo_triage: str | None = Header(default=None),
) -> models.User | None:
    """Resolve current user if session exists or if demo staff header is provided."""
    from app.services import auth_service

    token = extract_token(request)
    if token:
        res = auth_service.get_user_from_token(db, token)
        if res is not None:
            user, _ = res
            return user

    # Fallback to demo doctor/triage headers when demo mode is enabled
    if demo_enabled():
        if x_demo_doctor == "true":
            user = db.get(models.User, DEMO_DOCTOR_ID)
            if user and user.is_active:
                return user
        if x_demo_triage == "true":
            user = db.get(models.User, DEMO_TRIAGE_ID)
            if user and user.is_active:
                return user

    return None


def get_current_auth_user(
    request: Request,
    db: Session = Depends(get_db),
    x_demo_doctor: str | None = Header(default=None),
    x_demo_triage: str | None = Header(default=None),
) -> models.User:
    """Require an authenticated user of any role."""
    user = get_optional_auth_user(request, db, x_demo_doctor, x_demo_triage)
    if user is None:
        raise WorkflowError("AUTH_REQUIRED", "Authentication is required.", 401)
    return user


def require_doctor(
    request: Request,
    db: Session = Depends(get_db),
    x_demo_doctor: str | None = Header(default=None),
) -> models.User:
    """Require an authenticated user with role='doctor'."""
    user = get_optional_auth_user(request, db, x_demo_doctor=x_demo_doctor)
    if user is None:
        raise WorkflowError("AUTH_REQUIRED", "A configured doctor identity is required.", 401)
    if user.role != "doctor":
        raise WorkflowError("FORBIDDEN", "Doctor access is required.", 403)
    if not user.is_active:
        raise WorkflowError("FORBIDDEN", "Account is inactive.", 403)
    return user


# Backward compatibility alias
get_current_user = require_doctor


def require_triage(
    request: Request,
    db: Session = Depends(get_db),
    x_demo_doctor: str | None = Header(default=None),
    x_demo_triage: str | None = Header(default=None),
) -> models.User:
    """Require an authenticated staff member with triage or doctor permission."""
    user = get_optional_auth_user(
        request, db, x_demo_doctor=x_demo_doctor, x_demo_triage=x_demo_triage
    )
    if user is None:
        raise WorkflowError("AUTH_REQUIRED", "Triage staff identity is required.", 401)
    if user.role not in ("triage", "doctor"):
        raise WorkflowError("FORBIDDEN", "Triage staff access is required.", 403)
    if not user.is_active:
        raise WorkflowError("FORBIDDEN", "Account is inactive.", 403)
    return user


def require_staff(
    request: Request,
    db: Session = Depends(get_db),
    x_demo_doctor: str | None = Header(default=None),
    x_demo_triage: str | None = Header(default=None),
) -> models.User:
    """Require an authenticated staff member (doctor, triage, or admin)."""
    user = get_optional_auth_user(
        request, db, x_demo_doctor=x_demo_doctor, x_demo_triage=x_demo_triage
    )
    if user is None:
        raise WorkflowError("AUTH_REQUIRED", "Staff identity is required.", 401)
    if user.role not in ("doctor", "triage", "admin"):
        raise WorkflowError("FORBIDDEN", "Staff access is required.", 403)
    if not user.is_active:
        raise WorkflowError("FORBIDDEN", "Account is inactive.", 403)
    return user


def require_patient(user: models.User = Depends(get_current_auth_user)) -> models.User:
    """Require an authenticated patient account."""
    if user.role != "patient":
        raise WorkflowError("FORBIDDEN", "Patient access is required.", 403)
    if not user.is_active:
        raise WorkflowError("FORBIDDEN", "Account is inactive.", 403)
    return user


def require_patient_or_demo(
    user: models.User | None = Depends(get_optional_auth_user),
) -> models.User | None:
    """Allow an anonymous patient only for an explicitly enabled demo kiosk."""
    if user is None:
        if demo_enabled():
            return None
        raise WorkflowError("AUTH_REQUIRED", "Authentication is required.", 401)
    if user.role != "patient":
        raise WorkflowError("FORBIDDEN", "Patient access is required.", 403)
    if not user.is_active:
        raise WorkflowError("FORBIDDEN", "Account is inactive.", 403)
    return user


def require_assigned_doctor_session(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_doctor),
) -> models.User:
    """Authorize a doctor against both visit assignment and hospital membership."""
    from app.services import doctor_routing, intake

    session = intake.get_session(db, str(session_id))
    # Demo-only compatibility for historical unowned fixtures is centralized in
    # verify_session_access; owned sessions always require explicit assignment.
    intake.verify_session_access(db, session, user)
    if session.selected_doctor_id is not None:
        doctor_routing.require_assigned_doctor(db, session, user)
    return user
