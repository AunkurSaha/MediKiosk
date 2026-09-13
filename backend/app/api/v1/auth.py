import os

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app import models, schemas
from app.api.deps import (
    SESSION_COOKIE_NAME,
    extract_token,
    get_current_auth_user,
)
from app.core import phone
from app.core.config import demo_enabled
from app.core.errors import WorkflowError
from app.database import get_db
from app.services import auth_service
from app.services.sms_provider import get_sms_provider

router = APIRouter()


def _set_session_cookie(response: Response, token: str) -> None:
    is_production = os.getenv("APP_ENV", "development").lower() == "production"
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=is_production,
        max_age=7 * 24 * 3600,
        path="/",
    )


def _delete_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
    )


@router.post("/otp/request", response_model=schemas.OtpRequestResponse)
def request_otp_endpoint(
    req: schemas.OtpRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    ip = request.client.host if request.client else None
    ua = request.headers.get("User-Agent")
    return auth_service.request_otp(
        db,
        phone_raw=req.phone_number,
        ip_address=ip,
        user_agent=ua,
    )


@router.post("/otp/verify", response_model=schemas.LoginResponse)
def verify_otp_endpoint(
    req: schemas.OtpVerifyRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    ip = request.client.host if request.client else None
    ua = request.headers.get("User-Agent")
    user, raw_token, _ = auth_service.verify_otp(
        db,
        phone_raw=req.phone_number,
        otp_candidate=req.otp,
        ip_address=ip,
        user_agent=ua,
    )
    _set_session_cookie(response, raw_token)
    return schemas.LoginResponse(
        success=True,
        user=auth_service.get_auth_user_response(db, user),
        token=raw_token,
    )


@router.post("/logout", response_model=schemas.LogoutResponse)
def logout_endpoint(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    token = extract_token(request)
    if token:
        auth_service.logout_session(db, token)
    _delete_session_cookie(response)
    return schemas.LogoutResponse(success=True, message="Logged out successfully.")


@router.get("/me", response_model=schemas.AuthUserResponse)
def get_me(
    user: models.User = Depends(get_current_auth_user),
    db: Session = Depends(get_db),
):
    return auth_service.get_auth_user_response(db, user)


@router.post("/demo-login", response_model=schemas.LoginResponse)
def demo_login_endpoint(
    req: schemas.DemoLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    if not demo_enabled():
        raise WorkflowError("FORBIDDEN", "Demo login is disabled in production.", 403)
    ip = request.client.host if request.client else None
    ua = request.headers.get("User-Agent")
    user, raw_token, _ = auth_service.demo_login(
        db,
        role=req.role,
        hospital_id=req.hospital_id,
        specialty=req.specialty,
        ip_address=ip,
        user_agent=ua,
    )
    _set_session_cookie(response, raw_token)
    return schemas.LoginResponse(
        success=True,
        user=auth_service.get_auth_user_response(db, user),
        token=raw_token,
    )


@router.post("/staff-login", response_model=schemas.LoginResponse)
def staff_login_endpoint(
    req: schemas.StaffLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    ip = request.client.host if request.client else None
    ua = request.headers.get("User-Agent")
    user, raw_token, _ = auth_service.staff_login(
        db,
        identifier=req.identifier,
        password=req.password,
        hospital_id=req.hospital_id,
        specialty=req.specialty,
        ip_address=ip,
        user_agent=ua,
    )
    _set_session_cookie(response, raw_token)
    return schemas.LoginResponse(
        success=True,
        user=auth_service.get_auth_user_response(db, user),
        token=raw_token,
    )


@router.post("/staff-register", response_model=schemas.LoginResponse)
def staff_register_endpoint(
    req: schemas.StaffRegisterRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    ip = request.client.host if request.client else None
    ua = request.headers.get("User-Agent")
    user, raw_token, _ = auth_service.register_staff(
        db,
        name=req.name,
        role=req.role,
        phone_raw=req.phone_number,
        email=req.email,
        password=req.password,
        hospital_id=req.hospital_id,
        specialty=req.specialty,
        qualification=req.qualification,
        ip_address=ip,
        user_agent=ua,
    )
    _set_session_cookie(response, raw_token)
    return schemas.LoginResponse(
        success=True,
        user=auth_service.get_auth_user_response(db, user),
        token=raw_token,
    )


@router.post("/staff-otp/request", response_model=schemas.OtpRequestResponse)
def staff_otp_request_endpoint(
    req: schemas.OtpRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    ip = request.client.host if request.client else None
    ua = request.headers.get("User-Agent")
    res = auth_service.request_staff_otp(
        db,
        phone_raw=req.phone_number,
        ip_address=ip,
        user_agent=ua,
    )
    return schemas.OtpRequestResponse(**res)


@router.post("/staff-otp/verify", response_model=schemas.LoginResponse)
def staff_otp_verify_endpoint(
    req: schemas.OtpVerifyRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    ip = request.client.host if request.client else None
    ua = request.headers.get("User-Agent")
    user, raw_token, _ = auth_service.verify_staff_otp(
        db,
        phone_raw=req.phone_number,
        otp_candidate=req.otp,
        ip_address=ip,
        user_agent=ua,
    )
    _set_session_cookie(response, raw_token)
    return schemas.LoginResponse(
        success=True,
        user=auth_service.get_auth_user_response(db, user),
        token=raw_token,
    )



@router.get("/dev/last-otp")
def get_dev_last_otp(phone_number: str):
    """Test-only sink to retrieve OTP in development/test mode without live SMS.

    Strictly rejected in production.
    """
    if not (demo_enabled() or os.getenv("APP_ENV", "").lower() == "test"):
        raise WorkflowError("FORBIDDEN", "Endpoint strictly forbidden in production.", 403)
    canonical = phone.normalize_phone_number(phone_number)
    sms_provider = get_sms_provider()
    otp = sms_provider.get_last_dev_otp(canonical) if hasattr(sms_provider, "get_last_dev_otp") else None
    if not otp:
        raise WorkflowError("NOT_FOUND", "No OTP found in development sink for this phone number.", 404)
    return {"phone_number": canonical, "otp": otp}
