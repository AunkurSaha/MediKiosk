import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app import models
from app.api.deps import DEMO_DOCTOR_ID
from tests.test_documents import STAFF, fixture


def setup_session(client, database, *, medication_answer=None, allergy_answer=None):
    session_id = str(uuid.uuid4())
    assert (
        client.post(
            "/api/sessions",
            json={
                "id": session_id,
                "patient": {"name": "Synthetic Phase Seven"},
                "hospital_token": f"P7-{session_id[:8]}",
                "language": "en",
            },
        ).status_code
        == 201
    )
    assert (
        client.put(
            f"/api/sessions/{session_id}/consent",
            json={
                "voice_processing": False,
                "document_processing": True,
                "share_with_doctor": True,
            },
        ).status_code
        == 200
    )
    for field, value in (
        ("medications", medication_answer),
        ("allergies", allergy_answer),
    ):
        if value is not None:
            database.add(
                models.InterviewAnswer(
                    session_id=session_id,
                    question_id=field,
                    field=field,
                    value_json=json.dumps({"status": "answered", "value": value}),
                    raw_value=value,
                    source="typed",
                    language="en",
                    verification_status="patient_reported",
                )
            )
    database.flush()
    return session_id


def upload(client, session_id, name="prescription"):
    response = client.post(
        f"/api/sessions/{session_id}/documents",
        files={"file": (f"{name}.png", fixture(name), "image/png")},
    )
    assert response.status_code == 201
    return response.json()


def medical_facts(client, session_id):
    response = client.get(f"/api/doctor/sessions/{session_id}/medical-facts", headers=STAFF)
    assert response.status_code == 200
    return response.json()


def keep_only_medication(database, session_id, name):
    rows = list(
        database.scalars(
            select(models.MedicationFact).where(models.MedicationFact.session_id == session_id)
        )
    )
    for row in rows:
        if name.casefold() not in row.name.casefold():
            row.verification_status = "rejected"
    database.flush()
    return next(row for row in rows if name.casefold() in row.name.casefold())


def test_fact_api_is_staff_only_and_preserves_source_and_unknowns(client, database):
    session_id = setup_session(client, database)
    document = upload(client, session_id, "lab_missing_flag")
    assert client.get(f"/api/doctor/sessions/{session_id}/medical-facts").status_code == 401
    assert client.get(f"/api/sessions/{session_id}/medical-facts").status_code == 404
    result = medical_facts(client, session_id)
    assert result["counts"] == {"unverified": 1, "verified": 0, "rejected": 0}
    fact = result["labs"][0]
    assert fact["current"]["flag"] is None
    assert fact["current"]["observation_timestamp"] is None
    assert fact["source"]["document_id"] == document["id"]
    assert fact["source"]["extraction_id"] == document["extractions"][0]["id"]
    assert fact["source"]["source_location"] is None
    assert fact["source"]["raw_text"] == document["extractions"][0]["raw_text"]


def test_rejected_source_is_not_a_current_medical_fact(client, database):
    session_id = setup_session(client, database)
    document = upload(client, session_id)
    extraction = database.get(models.DocumentExtraction, document["extractions"][0]["id"])
    extraction.verification_status = "rejected"
    database.flush()
    result = medical_facts(client, session_id)
    assert result["medications"] == []
    assert result["rejected_medications"] == []
    assert result["counts"] == {"unverified": 0, "verified": 0, "rejected": 0}


def test_fact_review_preserves_original_and_adds_revision(client, database):
    session_id = setup_session(client, database)
    upload(client, session_id)
    fact = keep_only_medication(database, session_id, "Paracetamol")
    original_name = fact.name
    response = client.patch(
        f"/api/doctor/sessions/{session_id}/medical-facts/medications/{fact.id}",
        headers=STAFF,
        json={
            "expected_version": 0,
            "status": "verified",
            "correction": {"name": "Paracetamol (source checked)", "route": None},
            "notes": "Compared with synthetic source.",
        },
    )
    assert response.status_code == 200
    reviewed = response.json()
    assert reviewed["original"]["name"] == original_name
    assert reviewed["current"]["name"] == "Paracetamol (source checked)"
    assert reviewed["current"]["route"] is None
    assert reviewed["review_version"] == 1
    assert reviewed["verified_by"] == DEMO_DOCTOR_ID
    assert reviewed["revisions"][0]["corrected_data"]["name"] == reviewed["current"]["name"]
    database.refresh(fact)
    assert fact.name == original_name
    revision = database.scalar(
        select(models.MedicalFactRevision).where(models.MedicalFactRevision.fact_id == fact.id)
    )
    assert revision.original_data["name"] == original_name
    assert revision.reviewer_id == DEMO_DOCTOR_ID


def test_fact_review_rejects_anonymous_forgery_stale_version_and_locked_state(client, database):
    session_id = setup_session(client, database)
    upload(client, session_id, "lab_missing_flag")
    fact = database.scalar(select(models.LabFact).where(models.LabFact.session_id == session_id))
    path = f"/api/doctor/sessions/{session_id}/medical-facts/labs/{fact.id}"
    payload = {"expected_version": 0, "status": "verified"}
    assert client.patch(path, json=payload).status_code == 401
    forged = {**payload, "reviewer_id": "forged"}
    assert client.patch(path, headers=STAFF, json=forged).status_code == 422
    assert client.patch(path, headers=STAFF, json=payload).status_code == 200
    stale = client.patch(path, headers=STAFF, json=payload)
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "FACT_VERSION_CONFLICT"
    session = database.get(models.Session, session_id)
    session.status = "confirmed"
    database.flush()
    locked = client.patch(
        path,
        headers=STAFF,
        json={"expected_version": 1, "status": "rejected"},
    )
    assert locked.status_code == 409
    assert locked.json()["error"]["code"] == "SESSION_LOCKED"


def test_fact_review_rejection_is_separated_and_does_not_log_clinical_values(
    client, database, caplog
):
    session_id = setup_session(client, database)
    upload(client, session_id)
    fact = keep_only_medication(database, session_id, "Paracetamol")
    response = client.patch(
        f"/api/doctor/sessions/{session_id}/medical-facts/medications/{fact.id}",
        headers=STAFF,
        json={"expected_version": 0, "status": "rejected", "notes": "Synthetic review"},
    )
    assert response.status_code == 200
    result = medical_facts(client, session_id)
    assert result["medications"] == []
    assert fact.id in [item["id"] for item in result["rejected_medications"]]
    assert fact.name not in caplog.text


def test_timeline_orders_known_dates_and_separates_unknown_without_duplicates(client, database):
    session_id = setup_session(client, database)
    upload(client, session_id)
    fact = keep_only_medication(database, session_id, "Paracetamol")
    fact.start_date = datetime(2026, 8, 16, tzinfo=timezone.utc)
    database.flush()
    first = client.get(f"/api/doctor/sessions/{session_id}/timeline", headers=STAFF)
    second = client.get(f"/api/doctor/sessions/{session_id}/timeline", headers=STAFF)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    result = first.json()
    timestamps = [entry["event_timestamp"] for entry in result["known_date"]]
    assert timestamps == sorted(timestamps)
    assert [entry["event_type"] for entry in result["known_date"]] == [
        "document",
        "medication_started",
    ]
    assert len({entry["id"] for entry in result["known_date"] + result["unknown_date"]}) == len(
        result["known_date"] + result["unknown_date"]
    )
    assert all(entry["source"]["source_id"] for entry in result["known_date"])


def test_timeline_keeps_unknown_lab_date_unknown(client, database):
    session_id = setup_session(client, database)
    upload(client, session_id, "lab_missing_flag")
    result = client.get(f"/api/doctor/sessions/{session_id}/timeline", headers=STAFF).json()
    lab = next(
        entry for entry in result["unknown_date"] if entry["event_type"] == "lab_observation"
    )
    assert lab["event_timestamp"] is None
    assert lab["date_status"] == "unknown"
    assert lab["date_precision"] == "unknown"


def test_medication_mismatch_and_missing_are_conservative_and_source_linked(client, database):
    session_id = setup_session(client, database, medication_answer="Paracetamol 250 mg")
    upload(client, session_id)
    keep_only_medication(database, session_id, "Paracetamol")
    result = client.get(f"/api/doctor/sessions/{session_id}/discrepancies", headers=STAFF).json()
    assert [item["type"] for item in result["items"]] == ["MEDICATION_MISMATCH"]
    item = result["items"][0]
    assert item["source_a"]["source_type"] == "patient_answer"
    assert item["source_b"]["document_id"]
    assert item["verification_state"] == "requires_clinician_review"
    assert "adherence" not in item["reason"].casefold()

    other_session = setup_session(client, database, medication_answer="Ibuprofen")
    upload(client, other_session)
    keep_only_medication(database, other_session, "Paracetamol")
    missing = client.get(
        f"/api/doctor/sessions/{other_session}/discrepancies", headers=STAFF
    ).json()["items"]
    assert [item["type"] for item in missing] == ["MEDICATION_MISSING_FROM_PATIENT_REPORT"]


def test_no_discrepancy_when_patient_evidence_is_missing_or_medication_matches(client, database):
    session_id = setup_session(client, database)
    upload(client, session_id)
    keep_only_medication(database, session_id, "Paracetamol")
    path = f"/api/doctor/sessions/{session_id}/discrepancies"
    assert client.get(path, headers=STAFF).json()["items"] == []

    matched = setup_session(client, database, medication_answer="Paracetamol 500 mg")
    upload(client, matched)
    keep_only_medication(database, matched, "Paracetamol")
    assert (
        client.get(f"/api/doctor/sessions/{matched}/discrepancies", headers=STAFF).json()["items"]
        == []
    )


def test_allergy_conflict_requires_an_explicit_structured_document_statement(client, database):
    session_id = setup_session(client, database, allergy_answer="Penicillin causes a rash")
    document = upload(client, session_id)
    extraction = database.get(models.DocumentExtraction, document["extractions"][0]["id"])
    unchanged = client.get(
        f"/api/doctor/sessions/{session_id}/discrepancies", headers=STAFF
    ).json()["items"]
    assert all(item["type"] != "ALLERGY_CONFLICT" for item in unchanged)
    extraction.structured_json = {
        **extraction.structured_json,
        "allergies": [
            {
                "statement": "no_known_allergies",
                "substance": None,
                "raw_text": "No known allergies",
            }
        ],
    }
    database.flush()
    items = client.get(f"/api/doctor/sessions/{session_id}/discrepancies", headers=STAFF).json()[
        "items"
    ]
    allergy = next(item for item in items if item["type"] == "ALLERGY_CONFLICT")
    assert allergy["source_a"]["source_type"] == "patient_answer"
    assert allergy["source_b"]["extraction_id"] == extraction.id


def test_lab_conflict_requires_same_explicit_time_test_and_unit(client, database):
    session_id = setup_session(client, database)
    first_doc = upload(client, session_id, "lab_missing_flag")
    second_doc = upload(client, session_id, "lab_missing_flag")
    facts = list(
        database.scalars(select(models.LabFact).where(models.LabFact.session_id == session_id))
    )
    assert len(facts) == 2
    observed = datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc)
    facts[0].observation_timestamp = observed
    facts[0].unit = "g/dL"
    facts[0].value = "10.5"
    facts[1].observation_timestamp = observed
    facts[1].unit = "g/dL"
    facts[1].value = "11.0"
    database.flush()
    path = f"/api/doctor/sessions/{session_id}/discrepancies"
    first = client.get(path, headers=STAFF).json()
    second = client.get(path, headers=STAFF).json()
    assert first == second
    conflict = next(item for item in first["items"] if item["type"] == "LAB_VALUE_CONFLICT")
    assert {conflict["source_a"]["document_id"], conflict["source_b"]["document_id"]} == {
        first_doc["id"],
        second_doc["id"],
    }
    facts[1].observation_timestamp = None
    database.flush()
    assert all(
        item["type"] != "LAB_VALUE_CONFLICT"
        for item in client.get(path, headers=STAFF).json()["items"]
    )
