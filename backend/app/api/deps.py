from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app import models
from app.core.config import demo_enabled
from app.core.errors import WorkflowError
from app.database import get_db

DEMO_DOCTOR_ID = "00000000-0000-4000-8000-000000000001"
SESSION_COOKIE_NAME = "medikiosk_session"


def extract_token(request: Request) -> str | None:
    """Extract session token from cookie or Authorization header."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        return token
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return None


def get_optional_auth_user(
    request: Request,
    db: Session = Depends(get_db),
    x_demo_doctor: str | None = Header(default=None),
) -> models.User | None:
    """Resolve current user if session exists or if demo doctor header is provided."""
    from app.services import auth_service

    token = extract_token(request)
    if token:
        res = auth_service.get_user_from_token(db, token)
        if res is not None:
            user, _ = res
            return user

    # Fallback to demo doctor header when demo mode is enabled
    if demo_enabled() and x_demo_doctor == "true":
        user = db.get(models.User, DEMO_DOCTOR_ID)
        if user and user.is_active:
            return user

    return None


def get_current_auth_user(
    request: Request,
    db: Session = Depends(get_db),
    x_demo_doctor: str | None = Header(default=None),
) -> models.User:
    """Require an authenticated user (patient or doctor)."""
    user = get_optional_auth_user(request, db, x_demo_doctor)
    if user is None:
        raise WorkflowError("AUTH_REQUIRED", "Authentication is required.", 401)
    return user


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    x_demo_doctor: str | None = Header(default=None),
) -> models.User:
    """Existing staff/doctor dependency.

    Accepts:
    1. Authenticated session with role="doctor"
    2. Demo doctor mode with X-Demo-Doctor: true when demo_enabled()
    """
    user = get_optional_auth_user(request, db, x_demo_doctor)
    if user is None:
        raise WorkflowError("AUTH_REQUIRED", "A configured doctor identity is required.", 401)
    if user.role != "doctor":
        raise WorkflowError("FORBIDDEN", "Doctor access is required.", 403)
    return user


def require_patient(user: models.User = Depends(get_current_auth_user)) -> models.User:
    """Require authenticated user account."""
    if not user.is_active:
        raise WorkflowError("FORBIDDEN", "Account is inactive.", 403)
    return user
