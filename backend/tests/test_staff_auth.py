from starlette.testclient import TestClient

from app import models
from app.api.deps import DEMO_DOCTOR_ID, DEMO_TRIAGE_ID
from app.core import security


def test_doctor_login_with_10_digit_phone_and_password(client: TestClient):
    response = client.post(
        "/api/auth/staff-login",
        json={
            "identifier": "9876500001",
            "password": "Doctor@123",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["user"]["role"] == "doctor"
    assert data["user"]["id"] == DEMO_DOCTOR_ID
    assert data["token"] is not None


def test_doctor_login_with_e164_phone_and_password(client: TestClient):
    response = client.post(
        "/api/auth/staff-login",
        json={
            "identifier": "+919876500001",
            "password": "Doctor@123",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["user"]["role"] == "doctor"


def test_doctor_login_with_email_and_password(client: TestClient):
    response = client.post(
        "/api/auth/staff-login",
        json={
            "identifier": "doctor@tests.invalid",
            "password": "Doctor@123",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["user"]["role"] == "doctor"


def test_triage_login_with_phone_and_password(client: TestClient):
    response = client.post(
        "/api/auth/staff-login",
        json={
            "identifier": "9876500002",
            "password": "Triage@123",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["user"]["role"] == "triage"
    assert data["user"]["id"] == DEMO_TRIAGE_ID
    assert data["token"] is not None


def test_staff_login_with_wrong_password_fails(client: TestClient):
    response = client.post(
        "/api/auth/staff-login",
        json={
            "identifier": "9876500001",
            "password": "WrongPassword!999",
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_staff_login_with_nonexistent_identifier_fails(client: TestClient):
    response = client.post(
        "/api/auth/staff-login",
        json={
            "identifier": "9111111111",
            "password": "AnyPassword!123",
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_patient_account_cannot_login_via_staff_portal(client: TestClient, database):
    # Create a patient user with a password
    patient_phone = "+919876599999"
    patient = database.query(models.User).filter(models.User.phone_number == patient_phone).first()
    if not patient:
        patient = models.User(
            name="Sneaky Patient",
            phone_number=patient_phone,
            role="patient",
            hashed_password=security.hash_password("Patient@123"),
            is_active=True,
        )
        database.add(patient)
        database.commit()
    else:
        patient.hashed_password = security.hash_password("Patient@123")
        database.commit()

    response = client.post(
        "/api/auth/staff-login",
        json={
            "identifier": "9876599999",
            "password": "Patient@123",
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
