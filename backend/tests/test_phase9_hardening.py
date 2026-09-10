"""
Phase 9 Tests: Doctor Verification Hardening, Field-Level Verification,
Audit Trail, Confirmed Summary Amendments, and Document Cross-Referencing.
"""
import uuid

from app import models
from app.api.deps import DEMO_DOCTOR_ID

STAFF = {"X-Demo-Doctor": "true"}
FIELDS = ("chief_complaint", "onset_duration", "medications", "allergies", "past_history")


def _seed_completed_session(client, patient_name="Phase9 Patient", complaint="Chest pain"):
    sid = str(uuid.uuid4())
    resp = client.post(
        "/api/sessions",
        json={
            "id": sid,
            "patient": {"name": patient_name},
            "hospital_token": f"HOSP-{sid[:8]}",
            "language": "en",
        },
    )
    assert resp.status_code == 201

    consent_resp = client.put(
        f"/api/sessions/{sid}/consent",
        json={"voice_processing": True, "document_processing": True, "share_with_doctor": True},
    )
    assert consent_resp.status_code == 200

    for f in FIELDS:
        val = complaint if f == "chief_complaint" else ("No known allergies" if f == "allergies" else "None")
        ans_resp = client.post(
            f"/api/sessions/{sid}/answers",
            json={
                "question_id": f,
                "field": f,
                "value": val,
                "raw_value": val,
                "source": "typed",
                "language": "en",
            },
        )
        assert ans_resp.status_code == 200

    comp_resp = client.post(f"/api/sessions/{sid}/complete")
    assert comp_resp.status_code == 200
    return sid


def test_field_verification_lifecycle(client, database):
    sid = _seed_completed_session(client, "Field Verify Patient", "Severe Headache")

    # 1. Fetch answers to get answer ID
    session_detail = client.get(f"/api/doctor/sessions/{sid}", headers=STAFF).json()
    answers = session_detail["answers"]
    assert len(answers) >= 1
    target_answer = answers[0]
    target_id = target_answer["id"]

    # 2. Get field verifications (initially empty)
    list_resp = client.get(f"/api/doctor/sessions/{sid}/field-verifications", headers=STAFF)
    assert list_resp.status_code == 200
    assert len(list_resp.json()["items"]) == 0

    # 3. Verify the field as verified
    verify_resp = client.post(
        f"/api/doctor/sessions/{sid}/field-verifications",
        headers=STAFF,
        json={
            "field_type": "interview_answer",
            "field_id": target_id,
            "status": "verified",
            "notes": "Confirmed directly with patient in clinic",
        },
    )
    assert verify_resp.status_code == 200
    record = verify_resp.json()
    assert record["status"] == "verified"
    assert record["version"] == 1
    assert record["verified_by"] == DEMO_DOCTOR_ID
    assert record["notes"] == "Confirmed directly with patient in clinic"
    assert len(record["revisions"]) == 1
    assert record["revisions"][0]["version"] == 1

    # Check interview_answers.verification_status updated in DB
    ans_db = database.get(models.InterviewAnswer, target_id)
    assert ans_db.verification_status == "clinician_verified"

    # 4. Update verification to flagged with optimistic locking
    flag_resp = client.post(
        f"/api/doctor/sessions/{sid}/field-verifications",
        headers=STAFF,
        json={
            "field_type": "interview_answer",
            "field_id": target_id,
            "status": "flagged",
            "notes": "Patient clarifies headache started 3 weeks ago",
            "expected_version": 1,
        },
    )
    assert flag_resp.status_code == 200
    updated_rec = flag_resp.json()
    assert updated_rec["status"] == "flagged"
    assert updated_rec["version"] == 2
    assert len(updated_rec["revisions"]) == 2

    # Check interview_answers.verification_status updated to flagged
    database.refresh(ans_db)
    assert ans_db.verification_status == "flagged"

    # 5. Conflict rejection on stale version
    conflict_resp = client.post(
        f"/api/doctor/sessions/{sid}/field-verifications",
        headers=STAFF,
        json={
            "field_type": "interview_answer",
            "field_id": target_id,
            "status": "verified",
            "expected_version": 1,  # Stale: current is 2
        },
    )
    assert conflict_resp.status_code == 409
    assert conflict_resp.json()["error"]["code"] == "CONFLICT"

    # 6. Verify a summary statement
    stmt_resp = client.post(
        f"/api/doctor/sessions/{sid}/field-verifications",
        headers=STAFF,
        json={
            "field_type": "summary_statement",
            "field_id": "stmt-allergy-001",
            "status": "verified",
            "notes": "Patient confirms no drug reactions",
        },
    )
    assert stmt_resp.status_code == 200
    assert stmt_resp.json()["field_type"] == "summary_statement"

    # 7. List verifications has 2 records
    list_after = client.get(f"/api/doctor/sessions/{sid}/field-verifications", headers=STAFF).json()
    assert len(list_after["items"]) == 2


def test_confirmed_summary_amendment(client, database):
    sid = _seed_completed_session(client, "Amendment Patient", "Chest tightness")

    # 1. Attempting to amend draft fails
    amend_fail = client.post(
        f"/api/doctor/sessions/{sid}/summary/amend",
        headers=STAFF,
        json={
            "amended_text": "Amended consultation note",
            "amendment_notes": "Added after ECG review",
        },
    )
    assert amend_fail.status_code == 409
    assert amend_fail.json()["error"]["code"] == "NOT_CONFIRMED"

    # 2. Save review then confirm the summary
    summary_data = client.get(f"/api/doctor/sessions/{sid}/summary", headers=STAFF).json()
    save_resp = client.put(
        f"/api/doctor/sessions/{sid}/summary",
        headers=STAFF,
        json={
            "expected_version": summary_data["version"],
            "reviewed_text": summary_data["reviewed_text"],
        },
    )
    assert save_resp.status_code == 200
    reviewed_summary = save_resp.json()
    assert reviewed_summary["status"] == "reviewed"

    confirm_resp = client.post(
        f"/api/doctor/sessions/{sid}/summary/confirm",
        headers=STAFF,
        json={"expected_version": reviewed_summary["version"]},
    )
    assert confirm_resp.status_code == 200
    confirmed = confirm_resp.json()
    assert confirmed["status"] == "confirmed"
    original_confirmed_text = confirmed["confirmed_text"]
    assert original_confirmed_text is not None

    # 3. Amend the confirmed summary
    amend_resp = client.post(
        f"/api/doctor/sessions/{sid}/summary/amend",
        headers=STAFF,
        json={
            "amended_text": original_confirmed_text + "\n\n## Addendum\nECG normal sinus rhythm. Patient discharged.",
            "amendment_notes": "ECG completed in triage and reviewed with attending.",
        },
    )
    assert amend_resp.status_code == 200
    amended = amend_resp.json()
    assert amended["status"] == "amended"
    assert amended["confirmed_text"] == original_confirmed_text  # Original is completely preserved!
    assert "ECG normal sinus rhythm" in amended["amended_text"]
    assert amended["amended_by"] == DEMO_DOCTOR_ID
    assert amended["amended_at"] is not None
    assert amended["amendment_notes"] == "ECG completed in triage and reviewed with attending."

    # 4. Check revision history includes the amendment
    revs_resp = client.get(f"/api/doctor/sessions/{sid}/summary/revisions", headers=STAFF)
    assert revs_resp.status_code == 200
    revs = revs_resp.json()
    amend_revs = [r for r in revs if r["revision_type"] == "amendment"]
    assert len(amend_revs) == 1
    assert amend_revs[0]["actor_type"] == "DOCTOR"
    assert amend_revs[0]["actor_user_id"] == DEMO_DOCTOR_ID
    assert amend_revs[0]["review_notes"] == "ECG completed in triage and reviewed with attending."


def test_audit_trail_endpoint(client, database):
    sid = _seed_completed_session(client, "Audit Patient", "Cough")

    # Perform field verification
    client.post(
        f"/api/doctor/sessions/{sid}/field-verifications",
        headers=STAFF,
        json={
            "field_type": "interview_answer",
            "field_id": "dummy-ans-id",
            "status": "verified",
            "notes": "Verified in clinic",
        },
    )

    # Fetch audit trail
    audit_resp = client.get(f"/api/doctor/sessions/{sid}/audit-trail", headers=STAFF)
    assert audit_resp.status_code == 200
    trail = audit_resp.json()
    assert trail["session_id"] == sid
    assert trail["total"] >= 2  # intake_completed + session_viewed / field_verified

    actions = [item["action"] for item in trail["items"]]
    assert "intake_completed" in actions
    assert "field_verified" in actions

    field_verified_item = next(i for i in trail["items"] if i["action"] == "field_verified")
    assert field_verified_item["actor_type"] == "doctor"
    assert field_verified_item["actor_user_id"] == DEMO_DOCTOR_ID


def test_cross_references_endpoint(client, database):
    sid = _seed_completed_session(client, "XRef Patient", "Shortness of breath")

    xref_resp = client.get(f"/api/doctor/sessions/{sid}/cross-references", headers=STAFF)
    assert xref_resp.status_code == 200
    data = xref_resp.json()
    assert data["session_id"] == sid
    assert "documents" in data
    assert "statement_cross_references" in data
    assert isinstance(data["statement_cross_references"], dict)


def test_phase9_security_and_forgery_rejection(client):
    sid = _seed_completed_session(client, "Security Patient", "Fever")

    # 1. Unauthenticated / non-staff access rejected
    anon_resp = client.get(f"/api/doctor/sessions/{sid}/field-verifications")
    assert anon_resp.status_code in (401, 403)

    anon_audit = client.get(f"/api/doctor/sessions/{sid}/audit-trail")
    assert anon_audit.status_code in (401, 403)

    anon_xref = client.get(f"/api/doctor/sessions/{sid}/cross-references")
    assert anon_xref.status_code in (401, 403)

    # 2. Reject extra forbidden fields in request (forged verified_by)
    forge_resp = client.post(
        f"/api/doctor/sessions/{sid}/field-verifications",
        headers=STAFF,
        json={
            "field_type": "interview_answer",
            "field_id": "dummy-id",
            "status": "verified",
            "verified_by": "malicious-hacker",  # extra forbidden field
        },
    )
    assert forge_resp.status_code == 422
