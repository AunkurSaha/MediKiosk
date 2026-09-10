"""
Phase 8 Tests: Deterministic Clinical Summary Drafting, Doctor Review,
Evidence Attribution, and Confirmation Locking.
"""
import uuid
from datetime import datetime, timezone

from app import models
from app.api.deps import DEMO_DOCTOR_ID
from app.services.clinical_summary import ClinicalSummaryService

STAFF = {"X-Demo-Doctor": "true"}
FIELDS = ("chief_complaint", "onset_duration", "medications", "allergies", "past_history")


def create_completed_session(client, session_id=None):
    sid = session_id or str(uuid.uuid4())
    res = client.post(
        "/api/sessions",
        json={
            "id": sid,
            "patient": {"name": "Rajesh Kumar"},
            "hospital_token": f"HOSP-{sid[:8]}",
            "language": "en",
        },
    )
    assert res.status_code == 201

    res = client.put(
        f"/api/sessions/{sid}/consent",
        json={"voice_processing": True, "document_processing": True, "share_with_doctor": True},
    )
    assert res.status_code == 200

    answers = {
        "chief_complaint": "chest pain and shortness of breath",
        "onset_duration": "started 2 hours ago",
        "medications": "Amlodipine 5mg once daily",
        "allergies": "No known drug allergies",
        "past_history": "Hypertension for 5 years",
    }
    for field in FIELDS:
        val = answers[field]
        res = client.post(
            f"/api/sessions/{sid}/answers",
            json={
                "question_id": field,
                "field": field,
                "value": val,
                "raw_value": val,
                "source": "typed",
                "language": "en",
            },
        )
        assert res.status_code == 200

    res = client.post(f"/api/sessions/{sid}/complete")
    assert res.status_code == 200
    return sid


def test_clinical_summary_service_deterministic_10_sections(client, database):
    """Verify that ClinicalSummaryService builds all 10 required sections deterministically."""
    sid = create_completed_session(client)

    # Add medical facts (lab, medication)
    lab = models.LabFact(
        id=str(uuid.uuid4()),
        session_id=sid,
        test_name="Troponin I",
        value="0.8",
        unit="ng/mL",
        flag="high",
        verification_status="verified",
    )
    database.add(lab)

    med = models.MedicationFact(
        id=str(uuid.uuid4()),
        session_id=sid,
        name="Amlodipine",
        dosage="5mg",
        frequency="OD",
        verification_status="verified",
    )
    database.add(med)

    doc = models.Document(
        id=str(uuid.uuid4()),
        session_id=sid,
        object_key="ecg_report.pdf",
        original_filename="ecg_report.pdf",
        media_type="application/pdf",
        file_size_bytes=1024,
        sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        document_type="lab_report",
        document_date=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    database.add(doc)

    alert = models.Alert(
        id=str(uuid.uuid4()),
        session_id=sid,
        rule_id="RF-CARD-001",
        rule_version="1.0",
        priority="CRITICAL",
        category="cardiovascular",
        reason="Potential emergency symptoms detected: chest pain radiating to left arm",
        triggering_facts_json={"chief_complaint": "chest_pain"},
    )
    database.add(alert)
    database.flush()

    draft_text, structured = ClinicalSummaryService.generate_draft(database, sid, draft_version=1)

    # Check 10 sections present
    section_titles = [s.title for s in structured.sections]
    expected_titles = [
        "1. Patient Information",
        "2. Chief Complaint",
        "3. History of Present Illness",
        "4. Relevant Medical History",
        "5. Current Medications",
        "6. Investigations / Laboratory Findings",
        "7. Clinical Timeline",
        "8. Safety Alerts",
        "9. Potential Discrepancies",
        "10. Unknown / Not Reported Information",
    ]
    for expected in expected_titles:
        assert expected in section_titles, f"Missing section: {expected}"

    # Verify deterministic markdown text contains key headers
    for title in expected_titles:
        assert f"## {title}" in draft_text

    # Verify no diagnostic assertion
    assert "Diagnosis:" not in draft_text
    assert "You have" not in draft_text
    assert "Prescribed:" not in draft_text

    # Verify evidence attribution is preserved
    assert len(structured.evidence_references) > 0
    source_types = {e.source_type for e in structured.evidence_references}
    assert "patient_answer" in source_types
    assert "medical_fact" in source_types
    assert "alert" in source_types

    # Check that each evidence entry has valid fields
    for ev in structured.evidence_references:
        assert ev.source_id is not None
        assert ev.source_type in [
            "patient_answer",
            "normalized_fact",
            "medical_fact",
            "document",
            "alert",
            "discrepancy",
            "timeline",
        ]


def test_clinical_summary_ayush_banner(client, database):
    """Verify AYUSH pathway includes clear demonstration and disclaimer notice."""
    sid = str(uuid.uuid4())
    client.post(
        "/api/sessions",
        json={
            "id": sid,
            "patient": {"name": "Sunita Sharma"},
            "hospital_token": f"HOSP-{sid[:8]}",
            "language": "hi",
        },
    )
    client.put(
        f"/api/sessions/{sid}/consent",
        json={"voice_processing": False, "document_processing": True, "share_with_doctor": True},
    )
    # Add an answer with ayush mention
    client.post(
        f"/api/sessions/{sid}/answers",
        json={
            "question_id": "chief_complaint",
            "field": "chief_complaint",
            "value": "joint pain ayurveda ayush consultation",
            "raw_value": "joint pain ayurveda ayush consultation",
            "source": "typed",
            "language": "hi",
        },
    )
    for field in ("onset_duration", "medications", "allergies", "past_history"):
        client.post(
            f"/api/sessions/{sid}/answers",
            json={
                "question_id": field,
                "field": field,
                "value": "none reported",
                "raw_value": "none reported",
                "source": "typed",
                "language": "hi",
            },
        )
    client.post(f"/api/sessions/{sid}/complete")

    draft_text, structured = ClinicalSummaryService.generate_draft(database, sid, draft_version=1)
    assert "AYUSH DEMONSTRATION PATHWAY" in draft_text
    assert "supportive documentation only" in draft_text.lower()


def test_doctor_summary_api_workflow(client, database):
    """
    Test full doctor workflow:
    1. GET summary returns draft & evidence
    2. PUT summary saves review with optimistic locking & revision
    3. Stale version PUT rejected (409)
    4. POST regenerate with edits requires replacement confirmation (409)
    5. POST regenerate with confirm_replacement succeeds
    6. POST confirm locks summary (immutable)
    7. Future edit or regenerate rejected once confirmed
    """
    sid = create_completed_session(client)

    # 1. GET summary
    res = client.get(f"/api/doctor/sessions/{sid}/summary", headers=STAFF)
    assert res.status_code == 200
    data = res.json()
    assert data["session_id"] == sid
    assert data["status"] == "generated"
    assert "## 1. Patient Information" in data["generated_text"]
    assert data["reviewed_text"] is not None
    assert data["confirmed_text"] is None
    assert len(data["evidence"]) > 0
    assert data["structured_summary"] is not None

    # 2. PUT summary (Doctor saves review)
    edit_payload = {
        "reviewed_text": "Clinician notes: Patient reports mild fever for 3 days. No red flags. Follow-up advised.",
        "expected_version": 1,
        "review_notes": "Reviewed and added clinician observations",
    }
    put_res = client.put(f"/api/doctor/sessions/{sid}/summary", headers=STAFF, json=edit_payload)
    assert put_res.status_code == 200
    saved = put_res.json()
    assert saved["reviewed_text"] == edit_payload["reviewed_text"]
    assert saved["status"] == "reviewed"
    assert saved["version"] == 2
    assert saved["draft_version"] == 1

    # 3. Optimistic locking: Stale version PUT fails
    stale_put = client.put(f"/api/doctor/sessions/{sid}/summary", headers=STAFF, json=edit_payload)
    assert stale_put.status_code == 409
    assert stale_put.json()["error"]["code"] in ("VERSION_CONFLICT", "STALE_DATA")

    # 4. POST regenerate without confirm_replacement fails due to manual edits
    regen_fail = client.post(
        f"/api/doctor/sessions/{sid}/summary/regenerate",
        headers=STAFF,
        json={"expected_version": 2, "confirm_replacement": False},
    )
    assert regen_fail.status_code == 409
    assert regen_fail.json()["error"]["code"] == "CONFIRM_REPLACEMENT_REQUIRED"

    # 5. POST regenerate with confirm_replacement=True succeeds
    regen_ok = client.post(
        f"/api/doctor/sessions/{sid}/summary/regenerate",
        headers=STAFF,
        json={"expected_version": 2, "confirm_replacement": True, "review_notes": "Regenerated after fact updates"},
    )
    assert regen_ok.status_code == 200
    regen_data = regen_ok.json()
    assert regen_data["version"] == 3
    assert regen_data["draft_version"] == 2
    # Reviewed text was reset to regenerated text
    assert regen_data["reviewed_text"] == regen_data["generated_text"]

    # 6. Check revisions history
    rev_res = client.get(f"/api/doctor/sessions/{sid}/summary/revisions", headers=STAFF)
    assert rev_res.status_code == 200
    revisions = rev_res.json()
    assert len(revisions) >= 3  # initial draft, edit, regenerate
    rev_types = [r["revision_type"] for r in revisions]
    assert "initial_draft" in rev_types
    assert "edit" in rev_types
    assert "regenerate" in rev_types

    # 7. Check evidence endpoint
    ev_res = client.get(f"/api/doctor/sessions/{sid}/summary/evidence", headers=STAFF)
    assert ev_res.status_code == 200
    evidence_list = ev_res.json()
    assert len(evidence_list) > 0

    # 8. POST confirm (Locks the summary)
    confirm_res = client.post(
        f"/api/doctor/sessions/{sid}/summary/confirm",
        headers=STAFF,
        json={"expected_version": 3, "review_notes": "Final clinical sign-off"},
    )
    assert confirm_res.status_code == 200
    confirmed = confirm_res.json()
    assert confirmed["status"] == "confirmed"
    assert confirmed["confirmed_text"] is not None
    assert confirmed["confirmed_by"] == DEMO_DOCTOR_ID
    assert confirmed["confirmed_at"] is not None

    # 9. Verify immutability: further edits rejected
    edit_after_confirm = client.put(
        f"/api/doctor/sessions/{sid}/summary",
        headers=STAFF,
        json={"reviewed_text": "Illegal change", "expected_version": 4},
    )
    assert edit_after_confirm.status_code == 409
    assert edit_after_confirm.json()["error"]["code"] == "CONFIRMED_IMMUTABLE"

    # 10. Verify immutability: further regeneration rejected
    regen_after_confirm = client.post(
        f"/api/doctor/sessions/{sid}/summary/regenerate",
        headers=STAFF,
        json={"expected_version": 4, "confirm_replacement": True},
    )
    assert regen_after_confirm.status_code == 409
    assert regen_after_confirm.json()["error"]["code"] == "CONFIRMED_IMMUTABLE"


def test_doctor_summary_security_unauthorized(client):
    """Verify unauthorized access without staff credentials is rejected."""
    sid = str(uuid.uuid4())
    assert client.get(f"/api/doctor/sessions/{sid}/summary").status_code == 401
    assert client.put(f"/api/doctor/sessions/{sid}/summary", json={"reviewed_text": "test"}).status_code == 401
    assert client.post(f"/api/doctor/sessions/{sid}/summary/regenerate", json={}).status_code == 401
    assert client.post(f"/api/doctor/sessions/{sid}/summary/confirm", json={}).status_code == 401
    assert client.get(f"/api/doctor/sessions/{sid}/summary/revisions").status_code == 401
    assert client.get(f"/api/doctor/sessions/{sid}/summary/evidence").status_code == 401
