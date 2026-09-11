from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.core import phone, security
from app.services.sms_provider import get_sms_provider


def test_phone_normalization_valid_variants():
    assert phone.normalize_phone_number("9876543210") == "+919876543210"
    assert phone.normalize_phone_number("09876543210") == "+919876543210"
    assert phone.normalize_phone_number("919876543210") == "+919876543210"
    assert phone.normalize_phone_number("+919876543210") == "+919876543210"
    assert phone.normalize_phone_number("+91 98765 43210") == "+919876543210"
    assert phone.normalize_phone_number("+91-98765-43210") == "+919876543210"
    assert phone.normalize_phone_number("(0) 9876543210") == "+919876543210"


def test_phone_normalization_invalid_rejected():
    with pytest.raises(Exception):
        phone.normalize_phone_number("1234567890")  # starts with 1
    with pytest.raises(Exception):
        phone.normalize_phone_number("98765")  # too short
    with pytest.raises(Exception):
        phone.normalize_phone_number("")
    with pytest.raises(Exception):
        phone.normalize_phone_number("abcdefghij")


def test_phone_masking():
    assert phone.mask_phone_number("+919876543210") == "+91******3210"
    assert phone.mask_phone_number("+919999999999") == "+91******9999"


def test_otp_generation_and_hashing():
    otp = security.generate_otp()
    assert len(otp) == 6
    assert otp.isdigit()

    salt_hex, hash_hex = security.hash_otp(otp)
    assert len(salt_hex) == 32  # 16 bytes hex
    assert len(hash_hex) == 64  # SHA-256 hex
    assert security.verify_otp(otp, salt_hex, hash_hex) is True
    assert security.verify_otp("000000" if otp != "000000" else "111111", salt_hex, hash_hex) is False


def test_request_otp_flow(client, database):
    test_phone = "+919876500001"
    res = client.post("/api/auth/otp/request", json={"phone_number": test_phone})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["masked_phone"] == "+91******0001"
    assert data["cooldown_seconds"] == 60
    assert data["delivery_mode"] == "mock"
    # Invariant: plaintext OTP must never be returned in API response
    assert "otp" not in data

    # Verify challenge in DB
    challenge = database.query(models.OTPChallenge).filter_by(phone_number=test_phone).first()
    assert challenge is not None
    assert challenge.consumed_at is None
    assert challenge.otp_hash is not None
    # Invariant: DB must never store plaintext OTP
    assert not hasattr(challenge, "otp")

    # In test mode, verify dev sink has recorded OTP
    sms_provider = get_sms_provider()
    dev_otp = sms_provider.get_last_dev_otp(test_phone)
    assert dev_otp is not None
    assert len(dev_otp) == 6


def test_resend_cooldown(client):
    test_phone = "+919876500002"
    # First request
    res1 = client.post("/api/auth/otp/request", json={"phone_number": test_phone})
    assert res1.status_code == 200

    # Immediate second request should be rejected by 60s cooldown
    res2 = client.post("/api/auth/otp/request", json={"phone_number": test_phone})
    assert res2.status_code == 429
    err = res2.json()["error"]
    assert err["code"] == "COOLDOWN_ACTIVE"


def test_verify_valid_otp(client, database):
    test_phone = "+919876500003"
    client.post("/api/auth/otp/request", json={"phone_number": test_phone})
    sms_provider = get_sms_provider()
    otp = sms_provider.get_last_dev_otp(test_phone)

    # Verify
    verify_res = client.post(
        "/api/auth/otp/verify",
        json={"phone_number": test_phone, "otp": otp},
    )
    assert verify_res.status_code == 200
    data = verify_res.json()
    assert data["success"] is True
    assert data["user"]["role"] == "patient"
    assert data["user"]["phone_verified"] is True
    assert data["user"]["phone_number"] == "+91******0003"
    assert "token" in data

    # Check cookies
    assert "medikiosk_session" in verify_res.cookies

    # Verify User created in DB with role=patient
    user = database.query(models.User).filter_by(phone_number=test_phone).first()
    assert user is not None
    assert user.role == "patient"
    assert user.phone_verified is True

    # Challenge is marked consumed
    challenge = database.query(models.OTPChallenge).filter_by(phone_number=test_phone).first()
    assert challenge.consumed_at is not None

    # Test /api/auth/me with session cookie
    me_res = client.get("/api/auth/me", cookies={"medikiosk_session": data["token"]})
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["id"] == user.id
    assert me_data["role"] == "patient"


def test_verify_invalid_otp_decrements_attempts(client, database):
    test_phone = "+919876500004"
    client.post("/api/auth/otp/request", json={"phone_number": test_phone})

    # Wrong OTP
    res = client.post(
        "/api/auth/otp/verify",
        json={"phone_number": test_phone, "otp": "000000"},
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "INVALID_OTP"

    challenge = database.query(models.OTPChallenge).filter_by(phone_number=test_phone).first()
    assert challenge.attempt_count == 1
    assert challenge.consumed_at is None


def test_max_attempts_lockout(client, database):
    test_phone = "+919876500005"
    client.post("/api/auth/otp/request", json={"phone_number": test_phone})

    # Fail 5 times
    for _ in range(5):
        client.post(
            "/api/auth/otp/verify",
            json={"phone_number": test_phone, "otp": "111111"},
        )

    # 6th attempt should be locked
    res = client.post(
        "/api/auth/otp/verify",
        json={"phone_number": test_phone, "otp": "111111"},
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "TOO_MANY_ATTEMPTS"


def test_consumed_otp_cannot_be_reused(client):
    test_phone = "+919876500006"
    client.post("/api/auth/otp/request", json={"phone_number": test_phone})
    otp = get_sms_provider().get_last_dev_otp(test_phone)

    # First verify succeeds
    res1 = client.post("/api/auth/otp/verify", json={"phone_number": test_phone, "otp": otp})
    assert res1.status_code == 200

    # Second verify of same challenge fails
    res2 = client.post("/api/auth/otp/verify", json={"phone_number": test_phone, "otp": otp})
    assert res2.status_code == 400
    assert res2.json()["error"]["code"] == "INVALID_OTP"


def test_expired_otp_rejected(client, database):
    test_phone = "+919876500007"
    client.post("/api/auth/otp/request", json={"phone_number": test_phone})
    otp = get_sms_provider().get_last_dev_otp(test_phone)

    # Backdate challenge expiry
    challenge = database.query(models.OTPChallenge).filter_by(phone_number=test_phone).first()
    challenge.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    database.commit()

    res = client.post("/api/auth/otp/verify", json={"phone_number": test_phone, "otp": otp})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "OTP_EXPIRED"


def test_logout_invalidates_session(client):
    test_phone = "+919876500008"
    client.post("/api/auth/otp/request", json={"phone_number": test_phone})
    otp = get_sms_provider().get_last_dev_otp(test_phone)
    verify_res = client.post("/api/auth/otp/verify", json={"phone_number": test_phone, "otp": otp})
    token = verify_res.json()["token"]

    # Authenticated me works
    me1 = client.get("/api/auth/me", cookies={"medikiosk_session": token})
    assert me1.status_code == 200

    # Logout
    logout_res = client.post("/api/auth/logout", cookies={"medikiosk_session": token})
    assert logout_res.status_code == 200

    # Subsequent request fails
    me2 = client.get("/api/auth/me", cookies={"medikiosk_session": token})
    assert me2.status_code == 401


def test_role_separation_patient_cannot_access_doctor(client):
    """Critical security boundary: patient phone verification MUST NOT grant doctor access."""
    test_phone = "+919876500009"
    client.post("/api/auth/otp/request", json={"phone_number": test_phone})
    otp = get_sms_provider().get_last_dev_otp(test_phone)
    verify_res = client.post("/api/auth/otp/verify", json={"phone_number": test_phone, "otp": otp})
    token = verify_res.json()["token"]

    # Patient tries to call a doctor endpoint with patient session
    doc_res = client.get("/api/doctor/sessions", cookies={"medikiosk_session": token})
    # Must be 403 Forbidden
    assert doc_res.status_code == 403
    assert doc_res.json()["error"]["code"] == "FORBIDDEN"


def test_bearer_authorization_header(client):
    test_phone = "+919876500010"
    client.post("/api/auth/otp/request", json={"phone_number": test_phone})
    otp = get_sms_provider().get_last_dev_otp(test_phone)
    verify_res = client.post("/api/auth/otp/verify", json={"phone_number": test_phone, "otp": otp})
    token = verify_res.json()["token"]

    # Use Authorization header instead of cookie
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["role"] == "patient"


def test_unauthenticated_me_rejected(client):
    res = client.get("/api/auth/me")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "AUTH_REQUIRED"


def test_demo_login(client):
    # Patient demo login
    res1 = client.post("/api/auth/demo-login", json={"role": "patient"})
    assert res1.status_code == 200
    assert res1.json()["user"]["role"] == "patient"

    # Doctor demo login
    res2 = client.post("/api/auth/demo-login", json={"role": "doctor"})
    assert res2.status_code == 200
    assert res2.json()["user"]["role"] == "doctor"

    # Doctor session can access doctor endpoint
    doc_token = res2.json()["token"]
    doc_res = client.get("/api/doctor/sessions", headers={"Authorization": f"Bearer {doc_token}"})
    assert doc_res.status_code == 200


def test_dev_last_otp_endpoint(client):
    test_phone = "+919876500011"
    client.post("/api/auth/otp/request", json={"phone_number": test_phone})

    dev_res = client.get(f"/api/auth/dev/last-otp?phone_number={test_phone}")
    assert dev_res.status_code == 200
    assert dev_res.json()["phone_number"] == test_phone
    assert len(dev_res.json()["otp"]) == 6
