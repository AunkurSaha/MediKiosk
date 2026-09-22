import pytest
from fastapi import status
from app import models
from app.core import security


def test_triage_endpoint_demo_headers(client):
    """Test that triage endpoint can be accessed with demo headers."""
    # Without any authentication -> 401
    response = client.get("/api/triage/ws-ticket")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    # With X-Demo-Triage: true -> 200
    response = client.get(
        "/api/triage/ws-ticket",
        headers={"X-Demo-Triage": "true"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert "ticket" in response.json()

    # With X-Demo-Doctor: true -> 200 (doctor role is allowed)
    response = client.get(
        "/api/triage/ws-ticket",
        headers={"X-Demo-Doctor": "true"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert "ticket" in response.json()

    # With wrong header value -> 401
    response = client.get(
        "/api/triage/ws-ticket",
        headers={"X-Demo-Triage": "false"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    # With header but wrong case -> should still work (we made it case-insensitive)
    response = client.get(
        "/api/triage/ws-ticket",
        headers={"X-Demo-Triage": "TRUE"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert "ticket" in response.json()


def test_triage_endpoint_patient_forbidden(client, database):
    """Test that a patient role cannot access triage endpoint."""
    # Create a patient user in the database
    patient_user = models.User(
        id="aaaaaaaa-aaaa-4000-8000-000000000003",
        name="Patient User",
        email="patient@test.invalid",
        phone_number="+919876500003",
        role="patient",
        hashed_password=security.hash_password("Patient@123"),
        is_active=True,
    )
    database.add(patient_user)
    database.commit()

    # Log in via staff-login to get a token (using email and password)
    login_response = client.post(
        "/api/auth/staff-login",
        json={"identifier": "patient@test.invalid", "password": "Patient@123"},
    )
    assert login_response.status_code == status.HTTP_200_OK
    token = login_response.json()["token"]

    # Use the token to access triage endpoint -> should be 403 (forbidden)
    response = client.get(
        "/api/triage/ws-ticket",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_triage_endpoint_doctor_authenticated(client, database):
    """Test that a doctor user can access triage endpoint via normal login."""
    # Use the demo doctor user already created in the database fixture
    # Log in via staff-login
    login_response = client.post(
        "/api/auth/staff-login",
        json={"identifier": "doctor@medikiosk.invalid", "password": "Doctor@123"},
    )
    assert login_response.status_code == status.HTTP_200_OK
    token = login_response.json()["token"]

    # Use the token to access triage endpoint -> should be 200
    response = client.get(
        "/api/triage/ws-ticket",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert "ticket" in response.json()


def test_triage_endpoint_triage_authenticated(client, database):
    """Test that a triage user can access triage endpoint via normal login."""
    # Use the demo triage user already created in the database fixture
    login_response = client.post(
        "/api/auth/staff-login",
        json={"identifier": "triage@medikiosk.invalid", "password": "Triage@123"},
    )
    assert login_response.status_code == status.HTTP_200_OK
    token = login_response.json()["token"]

    # Use the token to access triage endpoint -> should be 200
    response = client.get(
        "/api/triage/ws-ticket",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert "ticket" in response.json()