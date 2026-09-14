import json
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app import models
from app.api.deps import DEMO_DOCTOR_ID
from app.database import get_db
from app.main import app
from app.services.intake import FIELDS

DOCTOR = {"X-Demo-Doctor": "true"}


def create(client, language="en"):
    payload = {
        "id": str(uuid4()),
        "patient": {"name": "Synthetic Patient", "demo_abha_id": None},
        "hospital_token": "DEMO-104",
        "language": language,
    }
    response = client.post("/api/sessions", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"], payload


def test_patient_demographics_are_validated_and_persisted(client):
    payload = {
        "id": str(uuid4()),
        "patient": {
            "name": "Demographic Test Patient",
            "gender": "prefer_not_to_say",
            "age_years": 42,
            "height_cm": 168.5,
            "weight_kg": 64.2,
            "demo_abha_id": None,
        },
        "hospital_token": "DEMO-DEMOGRAPHICS",
        "language": "en",
    }
    created = client.post("/api/sessions", json=payload)
    assert created.status_code == 201, created.text
    patient = client.get(f"/api/sessions/{payload['id']}").json()["patient"]
    assert patient["gender"] == "prefer_not_to_say"
    assert patient["age_years"] == 42
    assert patient["height_cm"] == 168.5
    assert patient["weight_kg"] == 64.2

    invalid = {**payload, "id": str(uuid4()), "patient": {**payload["patient"], "age_years": 121}}
    assert client.post("/api/sessions", json=invalid).status_code == 422


def consent(client, session_id, agreed=True):
    return client.put(
        f"/api/sessions/{session_id}/consent",
        json={
            "voice_processing": False,
            "document_processing": False,
            "share_with_doctor": agreed,
        },
    )


def answer(client, session_id, field="chief_complaint", value="Synthetic history", **overrides):
    payload = {
        "question_id": field,
        "field": field,
        "value": value,
        "raw_value": value,
        "source": "typed",
        "language": "en",
    }
    payload.update(overrides)
    return client.post(f"/api/sessions/{session_id}/answers", json=payload)


def prepared(client):
    session_id, _ = create(client)
    assert consent(client, session_id).status_code == 200
    for field in FIELDS:
        assert answer(client, session_id, field, f"Reported {field}").status_code == 200
    response = client.post(f"/api/sessions/{session_id}/complete")
    assert response.status_code == 200, response.text
    return session_id


def test_full_intake_review_confirm_preserves_draft_and_audit(client, database):
    session_id = prepared(client)
    listing = client.get("/api/doctor/sessions", headers=DOCTOR).json()["items"]
    assert listing[0]["patient_name"] == "Synthetic Patient"
    detail = client.get(f"/api/doctor/sessions/{session_id}", headers=DOCTOR)
    assert detail.status_code == 200, detail.text
    data = detail.json()
    assert data["session"]["status"] == "ready_for_review"
    assert [a["raw_value"] for a in data["answers"]] == [f"Reported {f}" for f in FIELDS]
    assert all(a["verification_status"] == "patient_reported" for a in data["answers"])
    draft = data["summary"]["generated_text"]
    saved = client.put(
        f"/api/doctor/sessions/{session_id}/summary",
        headers=DOCTOR,
        json={"reviewed_text": "Reviewed patient-reported history.", "expected_version": 1},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] == 2
    confirmed = client.post(
        f"/api/doctor/sessions/{session_id}/summary/confirm",
        headers=DOCTOR,
        json={"expected_version": 2},
    )
    assert confirmed.status_code == 200, confirmed.text
    final = confirmed.json()
    assert final["confirmed_by"] == DEMO_DOCTOR_ID
    assert final["confirmed_at"].endswith("+00:00")
    assert final["generated_text"] == draft
    assert client.get(f"/api/sessions/{session_id}").json()["session"]["status"] == "confirmed"
    assert database.scalar(select(func.count()).select_from(models.SummaryRevision)) == 1
    events = database.scalars(select(models.AuditLog)).all()
    assert {"consent_recorded", "answer_recorded", "summary_reviewed", "summary_confirmed"} <= {
        e.action for e in events
    }
    assert "Reported" not in json.dumps([e.metadata_json for e in events])


@pytest.mark.parametrize("given", [None, False])
def test_consent_cannot_be_bypassed(client, given):
    session_id, _ = create(client)
    if given is not None:
        assert consent(client, session_id, given).status_code == 200
    assert answer(client, session_id).status_code == 403
    assert client.post(f"/api/sessions/{session_id}/complete").status_code == 403
    assert client.get(f"/api/doctor/sessions/{session_id}", headers=DOCTOR).status_code == 403
    assert client.get("/api/doctor/sessions", headers=DOCTOR).json()["items"] == []


def test_idempotent_session_consent_answers_completion(client, database):
    session_id, payload = create(client)
    assert client.post("/api/sessions", json=payload).json()["id"] == session_id
    assert database.scalar(select(func.count()).select_from(models.Patient)) == 1
    for _ in range(2):
        assert consent(client, session_id).status_code == 200
    assert database.scalar(select(func.count()).select_from(models.Consent)) == 1
    for field in FIELDS:
        for _ in range(2):
            assert answer(client, session_id, field).status_code == 200
    assert database.scalar(select(func.count()).select_from(models.InterviewAnswer)) == 5
    for _ in range(2):
        assert client.post(f"/api/sessions/{session_id}/complete").status_code == 200
    assert database.scalar(select(func.count()).select_from(models.ClinicalSummary)) == 1
    payload["patient"]["name"] = "Different person"
    assert client.post("/api/sessions", json=payload).status_code == 409


def test_correction_retains_original_and_resume_returns_latest(client, database):
    session_id, _ = create(client)
    consent(client, session_id)
    assert answer(client, session_id, value="Not sure").status_code == 200
    assert answer(client, session_id, value="Patient clarification").status_code == 200
    assert database.scalar(select(func.count()).select_from(models.InterviewAnswer)) == 2
    result = client.get(f"/api/sessions/{session_id}").json()
    assert len(result["answers"]) == 1
    assert result["answers"][0]["value"] == "Patient clarification"


@pytest.mark.parametrize(
    "overrides",
    [
        {"verification_status": "clinician_verified"},
        {"source": "clinician"},
        {"value": ""},
        {"raw_value": "Changed"},
        {"language": "bn"},
        {"question_id": "allergies"},
        {"confidence": "1"},
    ],
)
def test_invalid_or_forged_answer_rejected(client, overrides):
    session_id, _ = create(client)
    consent(client, session_id)
    assert answer(client, session_id, **overrides).status_code == 422


def test_required_answers_and_review_cannot_be_skipped(client):
    session_id, _ = create(client)
    consent(client, session_id)
    assert client.post(f"/api/sessions/{session_id}/complete").status_code == 422
    session_id = prepared(client)
    assert (
        client.post(
            f"/api/doctor/sessions/{session_id}/summary/confirm",
            headers=DOCTOR,
            json={"expected_version": 1},
        ).status_code
        == 409
    )


def test_confirmed_record_locked_and_confirmation_idempotent(client):
    session_id = prepared(client)
    base = f"/api/doctor/sessions/{session_id}/summary"
    saved = client.put(
        base, headers=DOCTOR, json={"reviewed_text": "Reviewed", "expected_version": 1}
    )
    assert saved.status_code == 200
    final = client.post(base + "/confirm", headers=DOCTOR, json={"expected_version": 2})
    assert final.status_code == 200
    again = client.post(base + "/confirm", headers=DOCTOR, json={"expected_version": 2})
    assert again.json()["confirmed_at"] == final.json()["confirmed_at"]
    assert (
        client.put(
            base, headers=DOCTOR, json={"reviewed_text": "Overwrite", "expected_version": 2}
        ).status_code
        == 409
    )
    assert answer(client, session_id).status_code == 409
    assert consent(client, session_id, False).status_code == 409


def test_stale_review_and_forged_confirmation_metadata_rejected(client):
    session_id = prepared(client)
    base = f"/api/doctor/sessions/{session_id}/summary"
    assert (
        client.put(
            base, headers=DOCTOR, json={"reviewed_text": "First", "expected_version": 1}
        ).status_code
        == 200
    )
    assert (
        client.put(
            base, headers=DOCTOR, json={"reviewed_text": "Stale", "expected_version": 1}
        ).json()["error"]["code"]
        == "VERSION_CONFLICT"
    )
    assert (
        client.put(
            base,
            headers=DOCTOR,
            json={"reviewed_text": "Spoof", "expected_version": 2, "confirmed_by": "someone"},
        ).status_code
        == 422
    )


def test_auth_and_missing_resources(client, monkeypatch):
    assert client.get("/api/doctor/sessions").status_code == 401
    assert client.get(f"/api/sessions/{uuid4()}").status_code == 404
    assert client.get("/api/sessions/bad-id").status_code == 422
    assert client.get("/api/health").json() == {"status": "ok"}
    monkeypatch.setenv("DEMO_MODE", "false")
    assert client.get("/api/doctor/sessions", headers=DOCTOR).status_code == 401


def test_role_enforced_even_in_demo(client, database):
    database.get(models.User, DEMO_DOCTOR_ID).role = "triage"
    database.commit()
    assert client.get("/api/doctor/sessions", headers=DOCTOR).status_code == 403


def test_database_failure_returns_no_false_success_or_details(client):
    previous = app.dependency_overrides[get_db]

    def failing():
        raise OperationalError("sensitive SQL", {}, Exception("private connection details"))
        yield

    app.dependency_overrides[get_db] = failing
    try:
        response = client.get("/api/health")
        assert response.status_code == 503
        assert "private" not in response.text and "sensitive" not in response.text
    finally:
        app.dependency_overrides[get_db] = previous


def test_multilingual_text_roundtrip(client):
    session_id, _ = create(client, "bn")
    consent(client, session_id)
    text = "নিশ্চিত নই"
    assert answer(client, session_id, value=text, language="bn").status_code == 200
    assert client.get(f"/api/sessions/{session_id}").json()["answers"][0]["raw_value"] == text
