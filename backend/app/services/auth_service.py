"""Authentication service managing mobile phone verification, OTP challenges,
session lifecycles, and audit trails.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app import models
from app.core import phone, security
from app.core.config import demo_enabled
from app.core.errors import WorkflowError
from app.services.sms_provider import get_sms_provider

logger = logging.getLogger(__name__)

OTP_COOLDOWN_SECONDS = 60
OTP_EXPIRY_MINUTES = 5
MAX_OTP_ATTEMPTS = 5
HOURLY_RATE_LIMIT = 5


def log_auth_audit(
    db: Session,
    action: str,
    entity_id: str,
    actor_user_id: str | None = None,
    actor_type: str = "patient",
    metadata: dict | None = None,
) -> None:
    """Safe audit logger for authentication events.

    Invariants:
    - Never logs plaintext OTPs or credentials.
    - Masks phone numbers in metadata.
    """
    safe_metadata = dict(metadata or {})
    # Strip any potential accidental secret leakage
    safe_metadata.pop("otp", None)
    safe_metadata.pop("raw_token", None)
    safe_metadata.pop("api_key", None)

    audit_entry = models.AuditLog(
        actor_user_id=actor_user_id,
        actor_type=actor_type,
        action=action,
        entity_type="auth",
        entity_id=entity_id,
        metadata_json=safe_metadata,
    )
    db.add(audit_entry)


def request_otp(
    db: Session,
    phone_raw: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    """Validate phone number, apply rate limits, create hashed OTP challenge, and dispatch SMS."""
    canonical_phone = phone.normalize_phone_number(phone_raw)
    masked_phone = phone.mask_phone_number(canonical_phone)
    now = datetime.now(timezone.utc)

    # 1. Cooldown check: 60 seconds between requests
    cooldown_cutoff = now - timedelta(seconds=OTP_COOLDOWN_SECONDS)
    recent_challenge = db.scalar(
        select(models.OTPChallenge)
        .where(
            models.OTPChallenge.phone_number == canonical_phone,
            models.OTPChallenge.created_at >= cooldown_cutoff,
        )
        .order_by(desc(models.OTPChallenge.created_at))
    )
    if recent_challenge is not None:
        elapsed = (now - recent_challenge.created_at.replace(tzinfo=timezone.utc)).total_seconds()
        remaining = max(1, int(OTP_COOLDOWN_SECONDS - elapsed))
        raise WorkflowError(
            "COOLDOWN_ACTIVE",
            f"Please wait {remaining} seconds before requesting a new OTP.",
            429,
        )

    # 2. Hourly rate limit check: max 5 requests per hour
    one_hour_ago = now - timedelta(hours=1)
    challenges_last_hour = (
        db.query(models.OTPChallenge)
        .filter(
            models.OTPChallenge.phone_number == canonical_phone,
            models.OTPChallenge.created_at >= one_hour_ago,
        )
        .count()
    )
    if challenges_last_hour >= HOURLY_RATE_LIMIT:
        log_auth_audit(
            db,
            "OTP_RATE_LIMITED",
            canonical_phone,
            metadata={"phone": masked_phone, "reason": "hourly_limit_exceeded"},
        )
        db.commit()
        raise WorkflowError(
            "RATE_LIMITED",
            "Too many OTP requests for this number. Please try again later.",
            429,
        )

    # 3. Cryptographically secure 6-digit OTP generation and salted PBKDF2 hashing
    otp_code = security.generate_otp()
    salt_hex, hash_hex = security.hash_otp(otp_code)
    expires_at = now + timedelta(minutes=OTP_EXPIRY_MINUTES)

    challenge = models.OTPChallenge(
        id=str(uuid.uuid4()),
        phone_number=canonical_phone,
        purpose="login",
        otp_salt=salt_hex,
        otp_hash=hash_hex,
        created_at=now,
        expires_at=expires_at,
        attempt_count=0,
        max_attempts=MAX_OTP_ATTEMPTS,
        consumed_at=None,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(challenge)
    db.flush()

    # 4. Dispatch OTP via SMS provider
    sms_provider = get_sms_provider()
    sms_provider.send_otp(canonical_phone, otp_code)

    # 5. Audit log
    log_auth_audit(
        db,
        "OTP_REQUESTED",
        challenge.id,
        metadata={
            "phone": masked_phone,
            "delivery_mode": sms_provider.delivery_mode,
            "expires_in": OTP_EXPIRY_MINUTES * 60,
        },
    )
    db.commit()

    return {
        "success": True,
        "message": "If the number is eligible, an OTP has been sent.",
        "expires_in": OTP_EXPIRY_MINUTES * 60,
        "cooldown_seconds": OTP_COOLDOWN_SECONDS,
        "delivery_mode": sms_provider.delivery_mode,
        "masked_phone": masked_phone,
    }


def verify_otp(
    db: Session,
    phone_raw: str,
    otp_candidate: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[models.User, str, models.AuthSession]:
    """Verify OTP challenge, mark consumed, provision or authenticate user, and establish session."""
    canonical_phone = phone.normalize_phone_number(phone_raw)
    masked_phone = phone.mask_phone_number(canonical_phone)
    now = datetime.now(timezone.utc)

    # Find the latest unconsumed challenge for this phone number
    challenge = db.scalar(
        select(models.OTPChallenge)
        .where(
            models.OTPChallenge.phone_number == canonical_phone,
            models.OTPChallenge.consumed_at.is_(None),
        )
        .order_by(desc(models.OTPChallenge.created_at))
    )

    if challenge is None:
        log_auth_audit(
            db,
            "OTP_VERIFICATION_FAILED",
            canonical_phone,
            metadata={"phone": masked_phone, "reason": "no_active_challenge"},
        )
        db.commit()
        raise WorkflowError("INVALID_OTP", "No active OTP challenge found. Please request a new OTP.", 400)

    # Check expiration
    expires_at = (
        challenge.expires_at.replace(tzinfo=timezone.utc)
        if challenge.expires_at.tzinfo is None
        else challenge.expires_at
    )
    if now > expires_at:
        log_auth_audit(
            db,
            "OTP_EXPIRED",
            challenge.id,
            metadata={"phone": masked_phone},
        )
        db.commit()
        raise WorkflowError("OTP_EXPIRED", "The OTP has expired. Please request a new OTP.", 400)

    # Check attempt count
    if challenge.attempt_count >= challenge.max_attempts:
        log_auth_audit(
            db,
            "OTP_LOCKED",
            challenge.id,
            metadata={"phone": masked_phone, "attempt_count": challenge.attempt_count},
        )
        db.commit()
        raise WorkflowError(
            "TOO_MANY_ATTEMPTS",
            "Maximum verification attempts exceeded. Please request a new OTP.",
            400,
        )

    # Constant-time verify
    is_valid = security.verify_otp(otp_candidate.strip(), challenge.otp_salt, challenge.otp_hash)
    if not is_valid:
        challenge.attempt_count += 1
        db.commit()
        remaining = max(0, challenge.max_attempts - challenge.attempt_count)
        log_auth_audit(
            db,
            "OTP_VERIFICATION_FAILED",
            challenge.id,
            metadata={
                "phone": masked_phone,
                "attempt_count": challenge.attempt_count,
                "remaining_attempts": remaining,
            },
        )
        db.commit()
        raise WorkflowError(
            "INVALID_OTP",
            f"Invalid OTP. {remaining} attempt(s) remaining.",
            400,
        )

    # Mark challenge consumed immediately
    challenge.consumed_at = now

    # Look up or create User (strictly with role="patient")
    user = db.scalar(select(models.User).where(models.User.phone_number == canonical_phone))
    if user is None:
        user = models.User(
            id=str(uuid.uuid4()),
            name="Patient",
            phone_number=canonical_phone,
            role="patient",
            phone_verified=True,
            phone_verified_at=now,
            is_active=True,
        )
        db.add(user)
        db.flush()
    else:
        user.phone_verified = True
        user.phone_verified_at = now
        if not user.role:
            user.role = "patient"

    # Create session token and AuthSession
    raw_token, token_hash = security.generate_session_token()
    session_expires_at = now + timedelta(days=7)

    auth_session = models.AuthSession(
        id=str(uuid.uuid4()),
        session_token_hash=token_hash,
        user_id=user.id,
        role=user.role,
        created_at=now,
        expires_at=session_expires_at,
        is_revoked=False,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(auth_session)
    db.flush()

    log_auth_audit(
        db,
        "OTP_VERIFIED",
        challenge.id,
        actor_user_id=user.id,
        actor_type=user.role,
        metadata={"phone": masked_phone},
    )
    log_auth_audit(
        db,
        "LOGIN_SUCCESS",
        auth_session.id,
        actor_user_id=user.id,
        actor_type=user.role,
        metadata={"phone": masked_phone, "method": "phone_otp"},
    )
    db.commit()
    db.refresh(user)
    return user, raw_token, auth_session


def get_user_from_token(db: Session, raw_token: str) -> tuple[models.User, models.AuthSession] | None:
    """Authenticate session token, returning User and AuthSession if active and unexpired."""
    if not raw_token:
        return None
    token_hash = security.hash_session_token(raw_token)
    now = datetime.now(timezone.utc)

    auth_session = db.scalar(
        select(models.AuthSession).where(
            models.AuthSession.session_token_hash == token_hash,
            models.AuthSession.is_revoked.is_(False),
        )
    )
    if auth_session is None:
        return None

    expires_at = (
        auth_session.expires_at.replace(tzinfo=timezone.utc)
        if auth_session.expires_at.tzinfo is None
        else auth_session.expires_at
    )
    if now > expires_at:
        return None

    user = db.get(models.User, auth_session.user_id)
    if user is None or not user.is_active:
        return None

    return user, auth_session


def logout_session(db: Session, raw_token: str) -> bool:
    """Invalidate session and log audit trail."""
    if not raw_token:
        return False
    token_hash = security.hash_session_token(raw_token)
    auth_session = db.scalar(
        select(models.AuthSession).where(
            models.AuthSession.session_token_hash == token_hash,
            models.AuthSession.is_revoked.is_(False),
        )
    )
    if auth_session is not None:
        auth_session.is_revoked = True
        log_auth_audit(
            db,
            "LOGOUT",
            auth_session.id,
            actor_user_id=auth_session.user_id,
            actor_type=auth_session.role,
        )
        db.commit()
        return True
    return False


def sync_doctor_memberships(
    db: Session,
    doctor_id: str,
    hospital_id: str | None = None,
    specialty: str | None = None,
    qualification: str | None = None,
    name: str | None = None,
) -> None:
    """Ensure doctor profile and active hospital/specialty memberships are synced."""
    profile = db.get(models.DoctorProfile, doctor_id)
    if profile is None:
        user = db.get(models.User, doctor_id)
        display_name = name or (user.name if user else "Doctor")
        profile = models.DoctorProfile(
            doctor_user_id=doctor_id,
            display_name=display_name,
            qualification=qualification or "MD / MBBS",
            active=True,
            accepting_patients=True,
        )
        db.add(profile)
        db.flush()
    else:
        if qualification:
            profile.qualification = qualification
        if name:
            profile.display_name = name

    if hospital_id:
        hospital = db.get(models.Hospital, hospital_id)
        if hospital:
            membership = db.scalar(
                select(models.DoctorHospitalMembership).where(
                    models.DoctorHospitalMembership.doctor_id == doctor_id,
                    models.DoctorHospitalMembership.hospital_id == hospital_id,
                )
            )
            if membership is None:
                db.add(
                    models.DoctorHospitalMembership(
                        id=str(uuid.uuid4()),
                        doctor_id=doctor_id,
                        hospital_id=hospital_id,
                        active=True,
                    )
                )
            else:
                membership.active = True

    if specialty:
        clean_spec = specialty.strip().upper()
        spec_membership = db.scalar(
            select(models.DoctorSpecialtyMembership).where(
                models.DoctorSpecialtyMembership.doctor_id == doctor_id,
                models.DoctorSpecialtyMembership.specialty_code == clean_spec,
            )
        )
        if spec_membership is None:
            db.add(
                models.DoctorSpecialtyMembership(
                    id=str(uuid.uuid4()),
                    doctor_id=doctor_id,
                    specialty_code=clean_spec,
                )
            )
    db.flush()


def get_auth_user_response(db: Session, user: models.User) -> "schemas.AuthUserResponse":
    from app import schemas
    from app.core import phone

    hospital_id = None
    hospital_name = None
    specialty = None
    specialties: list[str] = []
    qualification = None

    if user.role == "doctor":
        profile = db.get(models.DoctorProfile, user.id)
        if profile:
            qualification = profile.qualification

        hosp_row = db.execute(
            select(models.Hospital.id, models.Hospital.name)
            .join(
                models.DoctorHospitalMembership,
                models.DoctorHospitalMembership.hospital_id == models.Hospital.id,
            )
            .where(
                models.DoctorHospitalMembership.doctor_id == user.id,
                models.DoctorHospitalMembership.active.is_(True),
            )
        ).first()
        if hosp_row:
            hospital_id, hospital_name = hosp_row

        specs = db.scalars(
            select(models.DoctorSpecialtyMembership.specialty_code).where(
                models.DoctorSpecialtyMembership.doctor_id == user.id
            )
        ).all()
        specialties = list(specs)
        if specialties:
            specialty = specialties[0]

    return schemas.AuthUserResponse(
        id=user.id,
        name=user.name,
        role=user.role,
        phone_number=phone.mask_phone_number(user.phone_number) if user.phone_number else None,
        phone_verified=user.phone_verified,
        hospital_id=hospital_id,
        hospital_name=hospital_name,
        specialty=specialty,
        specialties=specialties,
        qualification=qualification,
    )


def demo_login(
    db: Session,
    role: str = "patient",
    hospital_id: str | None = None,
    specialty: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[models.User, str, models.AuthSession]:
    """1-click demo login explicitly restricted to non-production environments when DEMO_MODE=true."""
    if not demo_enabled():
        raise WorkflowError("FORBIDDEN", "Demo login is not available in production.", 403)

    now = datetime.now(timezone.utc)
    if role == "doctor":
        from app.api.deps import DEMO_DOCTOR_ID

        user = db.get(models.User, DEMO_DOCTOR_ID)
        if user is None:
            user = models.User(
                id=DEMO_DOCTOR_ID,
                name="Synthetic Doctor",
                email="doctor@tests.invalid",
                role="doctor",
                is_active=True,
            )
            db.add(user)
            db.flush()
        sync_doctor_memberships(
            db,
            doctor_id=user.id,
            hospital_id=hospital_id or "10000000-0000-4000-8000-000000000001",
            specialty=specialty or "CARDIOLOGY",
            qualification="MD, Cardiology",
            name=user.name,
        )
    elif role == "triage":
        from app.api.deps import DEMO_TRIAGE_ID

        user = db.get(models.User, DEMO_TRIAGE_ID)
        if user is None:
            user = models.User(
                id=DEMO_TRIAGE_ID,
                name="Demo Triage Staff",
                email="triage@tests.invalid",
                role="triage",
                is_active=True,
            )
            db.add(user)
            db.flush()
    else:
        demo_phone = "+919999999999"
        user = db.scalar(select(models.User).where(models.User.phone_number == demo_phone))
        if user is None:
            user = models.User(
                id=str(uuid.uuid4()),
                name="Demo Patient",
                phone_number=demo_phone,
                role="patient",
                phone_verified=True,
                phone_verified_at=now,
                is_active=True,
            )
            db.add(user)
            db.flush()

    raw_token, token_hash = security.generate_session_token()
    session_expires_at = now + timedelta(days=7)

    auth_session = models.AuthSession(
        id=str(uuid.uuid4()),
        session_token_hash=token_hash,
        user_id=user.id,
        role=user.role,
        created_at=now,
        expires_at=session_expires_at,
        is_revoked=False,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(auth_session)
    db.flush()
    log_auth_audit(
        db,
        "DEMO_LOGIN",
        auth_session.id,
        actor_user_id=user.id,
        actor_type=user.role,
        metadata={"role": user.role},
    )
    db.commit()
    db.refresh(user)
    return user, raw_token, auth_session


def staff_login(
    db: Session,
    identifier: str,
    password: str,
    hospital_id: str | None = None,
    specialty: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[models.User, str, models.AuthSession]:
    """Authenticate staff (doctor or triage) using phone number or email with password."""
    cleaned = identifier.strip()
    if not cleaned or not password:
        raise WorkflowError("INVALID_CREDENTIALS", "Please provide both identifier and password.", 401)

    # 1. Attempt phone normalization lookup
    user: models.User | None = None
    try:
        canonical_phone = phone.normalize_phone_number(cleaned)
        user = db.scalar(select(models.User).where(models.User.phone_number == canonical_phone))
    except WorkflowError:
        pass

    # 2. Fallback to direct email or phone match
    if user is None:
        user = db.scalar(
            select(models.User).where(
                (models.User.email == cleaned) | (models.User.phone_number == cleaned)
            )
        )

    # 3. Security checks
    if user is None or not user.is_active:
        raise WorkflowError("INVALID_CREDENTIALS", "Invalid staff credentials.", 401)

    if user.role not in ("doctor", "triage"):
        raise WorkflowError("FORBIDDEN", "Staff and management access only.", 403)

    if not user.hashed_password or not security.verify_password(password, user.hashed_password):
        raise WorkflowError("INVALID_CREDENTIALS", "Invalid staff credentials.", 401)

    if user.role == "doctor" and (hospital_id or specialty):
        sync_doctor_memberships(
            db,
            doctor_id=user.id,
            hospital_id=hospital_id,
            specialty=specialty,
            name=user.name,
        )

    now = datetime.now(timezone.utc)
    raw_token, token_hash = security.generate_session_token()
    session_expires_at = now + timedelta(days=7)

    auth_session = models.AuthSession(
        id=str(uuid.uuid4()),
        session_token_hash=token_hash,
        user_id=user.id,
        role=user.role,
        created_at=now,
        expires_at=session_expires_at,
        is_revoked=False,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(auth_session)
    db.flush()

    masked_id = phone.mask_phone_number(cleaned) if (cleaned.startswith("+") or cleaned.isdigit()) else cleaned
    log_auth_audit(
        db,
        "STAFF_LOGIN",
        auth_session.id,
        actor_user_id=user.id,
        actor_type=user.role,
        metadata={"role": user.role, "identifier": masked_id},
    )
    db.commit()
    db.refresh(user)
    return user, raw_token, auth_session


def register_staff(
    db: Session,
    name: str,
    role: str,
    phone_raw: str,
    email: str | None,
    password: str,
    hospital_id: str | None = None,
    specialty: str | None = None,
    qualification: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[models.User, str, models.AuthSession]:
    """Register a new staff member (doctor or triage) and create an active session."""
    clean_name = name.strip()
    if not clean_name:
        raise WorkflowError("INVALID_DATA", "Full name is required.", 422)

    if role not in ("doctor", "triage"):
        raise WorkflowError("INVALID_ROLE", "Role must be 'doctor' or 'triage'.", 422)

    if not password or len(password) < 6:
        raise WorkflowError("WEAK_PASSWORD", "Password must be at least 6 characters.", 422)

    canonical_phone = phone.normalize_phone_number(phone_raw)

    existing_phone = db.scalar(select(models.User).where(models.User.phone_number == canonical_phone))
    if existing_phone:
        raise WorkflowError("USER_EXISTS", "A user is already registered with this mobile number.", 409)

    clean_email = email.strip().lower() if email and email.strip() else None
    if clean_email:
        existing_email = db.scalar(select(models.User).where(models.User.email == clean_email))
        if existing_email:
            raise WorkflowError("USER_EXISTS", "A user is already registered with this email address.", 409)

    hashed_pass = security.hash_password(password)
    user = models.User(
        id=str(uuid.uuid4()),
        name=clean_name,
        role=role,
        phone_number=canonical_phone,
        email=clean_email,
        hashed_password=hashed_pass,
        phone_verified=True,
        is_active=True,
    )
    db.add(user)
    db.flush()

    if role == "doctor":
        sync_doctor_memberships(
            db,
            doctor_id=user.id,
            hospital_id=hospital_id,
            specialty=specialty,
            qualification=qualification,
            name=clean_name,
        )

    now = datetime.now(timezone.utc)
    raw_token, token_hash = security.generate_session_token()
    session_expires_at = now + timedelta(days=7)

    auth_session = models.AuthSession(
        id=str(uuid.uuid4()),
        session_token_hash=token_hash,
        user_id=user.id,
        role=user.role,
        created_at=now,
        expires_at=session_expires_at,
        is_revoked=False,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(auth_session)
    db.flush()

    masked_phone = phone.mask_phone_number(canonical_phone)
    log_auth_audit(
        db,
        "STAFF_REGISTERED",
        auth_session.id,
        actor_user_id=user.id,
        actor_type=user.role,
        metadata={"role": user.role, "name": user.name, "phone": masked_phone},
    )
    db.commit()
    db.refresh(user)
    return user, raw_token, auth_session


def request_staff_otp(
    db: Session,
    phone_raw: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    """Request an OTP for an existing staff member (doctor or triage)."""
    canonical_phone = phone.normalize_phone_number(phone_raw)
    staff_user = db.scalar(select(models.User).where(models.User.phone_number == canonical_phone))
    if staff_user is None or staff_user.role not in ("doctor", "triage") or not staff_user.is_active:
        raise WorkflowError("NOT_FOUND", "No staff account found with this mobile number. Please register first or use password login.", 404)

    return request_otp(db, phone_raw, ip_address, user_agent)


def verify_staff_otp(
    db: Session,
    phone_raw: str,
    otp_candidate: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[models.User, str, models.AuthSession]:
    """Verify an OTP for staff login and create a session with doctor/triage authorization."""
    canonical_phone = phone.normalize_phone_number(phone_raw)
    staff_user = db.scalar(select(models.User).where(models.User.phone_number == canonical_phone))
    if staff_user is None or staff_user.role not in ("doctor", "triage") or not staff_user.is_active:
        raise WorkflowError("FORBIDDEN", "Staff access only.", 403)

    masked_phone = phone.mask_phone_number(canonical_phone)
    now = datetime.now(timezone.utc)

    challenge = db.scalar(
        select(models.OTPChallenge)
        .where(
            models.OTPChallenge.phone_number == canonical_phone,
            models.OTPChallenge.consumed_at.is_(None),
        )
        .order_by(desc(models.OTPChallenge.created_at))
    )

    if challenge is None:
        log_auth_audit(
            db,
            "OTP_VERIFICATION_FAILED",
            canonical_phone,
            metadata={"phone": masked_phone, "reason": "no_active_challenge"},
        )
        db.commit()
        raise WorkflowError("INVALID_OTP", "No active OTP challenge found. Please request a new OTP.", 400)

    expires_at = (
        challenge.expires_at.replace(tzinfo=timezone.utc)
        if challenge.expires_at.tzinfo is None
        else challenge.expires_at
    )
    if now > expires_at:
        log_auth_audit(db, "OTP_EXPIRED", challenge.id, metadata={"phone": masked_phone})
        db.commit()
        raise WorkflowError("OTP_EXPIRED", "The OTP has expired. Please request a new OTP.", 400)

    if challenge.attempt_count >= challenge.max_attempts:
        log_auth_audit(
            db,
            "OTP_LOCKED",
            challenge.id,
            metadata={"phone": masked_phone, "attempt_count": challenge.attempt_count},
        )
        db.commit()
        raise WorkflowError("TOO_MANY_ATTEMPTS", "Maximum verification attempts exceeded. Please request a new OTP.", 400)

    is_valid = security.verify_otp(otp_candidate.strip(), challenge.otp_salt, challenge.otp_hash)
    if not is_valid:
        challenge.attempt_count += 1
        db.commit()
        remaining = max(0, challenge.max_attempts - challenge.attempt_count)
        log_auth_audit(
            db,
            "OTP_VERIFICATION_FAILED",
            challenge.id,
            metadata={"phone": masked_phone, "remaining_attempts": remaining},
        )
        db.commit()
        raise WorkflowError("INVALID_OTP", f"Invalid OTP. {remaining} attempt(s) remaining.", 400)

    challenge.consumed_at = now
    staff_user.phone_verified = True

    raw_token, token_hash = security.generate_session_token()
    session_expires_at = now + timedelta(days=7)

    auth_session = models.AuthSession(
        id=str(uuid.uuid4()),
        session_token_hash=token_hash,
        user_id=staff_user.id,
        role=staff_user.role,
        created_at=now,
        expires_at=session_expires_at,
        is_revoked=False,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(auth_session)
    db.flush()

    log_auth_audit(
        db,
        "STAFF_OTP_LOGIN",
        auth_session.id,
        actor_user_id=staff_user.id,
        actor_type=staff_user.role,
        metadata={"role": staff_user.role, "phone": masked_phone},
    )
    db.commit()
    db.refresh(staff_user)
    return staff_user, raw_token, auth_session

