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


def demo_login(
    db: Session,
    role: str = "patient",
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
