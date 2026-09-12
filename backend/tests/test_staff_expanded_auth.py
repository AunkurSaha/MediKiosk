from fastapi.testclient import TestClient

from app.api.deps import DEMO_DOCTOR_ID, DEMO_TRIAGE_ID


def test_staff_register_doctor_success(client: TestClient):
    payload = {
        "name": "Dr. Sarah Jenkins",
        "role": "doctor",
        "phone_number": "9876543210",
        "email": "sarah.jenkins@hospital.invalid",
        "password": "SecurePassword123",
    }
    response = client.post("/api/auth/staff-register", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["success"] is True
    assert data["user"]["name"] == "Dr. Sarah Jenkins"
    assert data["user"]["role"] == "doctor"
    assert "medikiosk_session" in response.cookies


def test_staff_register_triage_success(client: TestClient):
    payload = {
        "name": "Nurse Alex Kumar",
        "role": "triage",
        "phone_number": "9876543211",
        "email": "alex.kumar@hospital.invalid",
        "password": "TriagePassword123",
    }
    response = client.post("/api/auth/staff-register", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["success"] is True
    assert data["user"]["name"] == "Nurse Alex Kumar"
    assert data["user"]["role"] == "triage"


def test_staff_register_duplicate_phone_rejected(client: TestClient):
    payload = {
        "name": "Duplicate Dr.",
        "role": "doctor",
        "phone_number": "9876500001",  # Already belongs to seeded demo doctor
        "password": "AnotherPassword123",
    }
    response = client.post("/api/auth/staff-register", json=payload)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "USER_EXISTS"


def test_staff_register_invalid_role_rejected(client: TestClient):
    payload = {
        "name": "Hacker Role",
        "role": "patient",  # Only doctor or triage allowed
        "phone_number": "9876543299",
        "password": "Password123",
    }
    response = client.post("/api/auth/staff-register", json=payload)
    assert response.status_code == 422


def test_staff_otp_request_non_staff_rejected(client: TestClient):
    # Unregistered phone number
    response = client.post("/api/auth/staff-otp/request", json={"phone_number": "9811111111"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_staff_otp_flow_doctor_success(client: TestClient):
    # Request OTP for registered doctor (phone: +919876500001)
    req_res = client.post("/api/auth/staff-otp/request", json={"phone_number": "9876500001"})
    assert req_res.status_code == 200, req_res.text
    assert req_res.json()["success"] is True

    # Retrieve OTP from dev sink
    dev_res = client.get("/api/auth/dev/last-otp?phone_number=%2B919876500001")
    assert dev_res.status_code == 200
    otp = dev_res.json()["otp"]

    # Verify OTP
    verify_res = client.post("/api/auth/staff-otp/verify", json={"phone_number": "9876500001", "otp": otp})
    assert verify_res.status_code == 200, verify_res.text
    data = verify_res.json()
    assert data["success"] is True
    assert data["user"]["role"] == "doctor"
    assert data["user"]["id"] == DEMO_DOCTOR_ID


def test_staff_otp_flow_triage_success(client: TestClient):
    # Request OTP for registered triage (phone: +919876500002)
    req_res = client.post("/api/auth/staff-otp/request", json={"phone_number": "9876500002"})
    assert req_res.status_code == 200, req_res.text

    dev_res = client.get("/api/auth/dev/last-otp?phone_number=%2B919876500002")
    assert dev_res.status_code == 200
    otp = dev_res.json()["otp"]

    verify_res = client.post("/api/auth/staff-otp/verify", json={"phone_number": "9876500002", "otp": otp})
    assert verify_res.status_code == 200, verify_res.text
    data = verify_res.json()
    assert data["success"] is True
    assert data["user"]["role"] == "triage"
    assert data["user"]["id"] == DEMO_TRIAGE_ID
