import uuid
import json
from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.api.deps import get_current_auth_user
from app.main import app
from app.services import clinical_coverage, continuity
from tests.test_adaptive import selected, submit, until


def _session(database, patient, *, status, completed_at, owner=None, doctor=None, hospital=None):
    row = models.Session(
        id=str(uuid.uuid4()),
        patient_id=patient.id,
        user_id=owner.id if owner else None,
        selected_doctor_id=doctor.id if doctor else None,
        hospital_id=hospital.id if hospital else None,
        hospital_token="C9",
        language="en",
        status=status,
        completed_at=completed_at,
    )
    database.add(row)
    database.flush()
    return row


def _evidence(database, session, *, field, value, concept=None):
    row = models.ClinicalEvidence(
        patient_id=session.patient_id,
        session_id=session.id,
        concept_code=concept,
        value_json=value,
        source_type="PATIENT_TEXT",
        source_id=str(uuid.uuid4()),
        stable_key="raw_answer",
        original_text=str(value),
        verification_status="PATIENT_CONFIRMED",
        metadata_json={"canonical_field": field},
    )
    database.add(row)
    database.flush()
    return row


def _fixture(database):
    patient = models.Patient(id=str(uuid.uuid4()), name="Continuity Patient")
    owner = models.User(id=str(uuid.uuid4()), name="Owner", role="patient", is_active=True)
    doctor = models.User(id=str(uuid.uuid4()), name="Doctor", role="doctor", is_active=True)
    other = models.User(id=str(uuid.uuid4()), name="Other", role="patient", is_active=True)
    colleague = models.User(id=str(uuid.uuid4()), name="Colleague", role="doctor", is_active=True)
    hospital = models.Hospital(code=f"C9-{uuid.uuid4().hex}", name="Continuity Hospital")
    database.add_all([patient, owner, doctor, other, colleague, hospital])
    database.flush()
    database.add_all(
        [
            models.DoctorProfile(doctor_user_id=doctor.id, display_name=doctor.name),
            models.DoctorProfile(doctor_user_id=colleague.id, display_name=colleague.name),
        ]
    )
    database.flush()
    database.add_all(
        [
            models.DoctorHospitalMembership(
                doctor_id=doctor.id, hospital_id=hospital.id, active=True
            ),
            models.DoctorHospitalMembership(
                doctor_id=colleague.id, hospital_id=hospital.id, active=True
            ),
        ]
    )
    now = datetime.now(timezone.utc)
    old = _session(
        database,
        patient,
        status="ready_for_review",
        completed_at=now - timedelta(days=3),
        owner=owner,
    )
    recent = _session(
        database, patient, status="confirmed", completed_at=now - timedelta(days=1), owner=owner
    )
    current = _session(
        database,
        patient,
        status="intake",
        completed_at=None,
        owner=owner,
        doctor=doctor,
        hospital=hospital,
    )
    database.add(
        models.Consent(
            session_id=current.id,
            voice_processing=False,
            document_processing=False,
            share_with_doctor=True,
        )
    )
    incomplete = _session(database, patient, status="intake", completed_at=None, owner=owner)
    database.commit()
    return owner, doctor, other, colleague, old, recent, current, incomplete


def test_prior_selection_is_same_patient_completed_and_most_recent(database):
    _, _, _, _, old, recent, current, incomplete = _fixture(database)
    assert [
        item.id for item in continuity.get_prior_completed_encounters(database, current.id)
    ] == [recent.id, old.id]
    assert continuity.get_most_recent_prior_encounter(database, current.id).id == recent.id
    assert incomplete.id not in {
        item.id for item in continuity.get_prior_completed_encounters(database, current.id)
    }


def test_continuity_keeps_historical_evidence_separate_and_compares_deterministically(database):
    _, _, _, _, _, recent, current, _ = _fixture(database)
    old_medication = _evidence(
        database,
        recent,
        field="medications",
        concept="MEDICATION_METFORMIN",
        value={"name": "Metformin", "dose": "500 mg"},
    )
    _evidence(database, current, field="chief_complaint", concept="HEADACHE", value="headache")
    before_answers = database.query(models.InterviewAnswer).count()
    before_evidence = database.query(models.ClinicalEvidence).count()
    first = continuity.snapshot(database, current.id)
    second = continuity.snapshot(database, current.id)
    assert first.model_dump() == second.model_dump()
    assert first.historical_evidence[0].evidence_id == old_medication.id
    assert first.changes.historical_unconfirmed[0].status == "HISTORICAL_ONLY"
    assert first.changes.new[0].status == "NEW"
    assert database.query(models.InterviewAnswer).count() == before_answers
    assert database.query(models.ClinicalEvidence).count() == before_evidence
    reconfirmed = _evidence(
        database,
        current,
        field="medications",
        concept="MEDICATION_METFORMIN",
        value={"name": "Metformin", "dose": "500 mg"},
    )
    reconfirmed.created_at = datetime.now(timezone.utc) + timedelta(seconds=1)
    assert continuity.snapshot(database, current.id).changes.unchanged[0].status == "UNCHANGED"
    changed = _evidence(
        database,
        current,
        field="medications",
        concept="MEDICATION_METFORMIN",
        value={"name": "Metformin", "dose": "1000 mg"},
    )
    changed.created_at = datetime.now(timezone.utc) + timedelta(seconds=2)
    assert continuity.snapshot(database, current.id).changes.changed[0].status == "CHANGED"


def test_continuity_api_enforces_owner_and_triage_is_forbidden(client, database):
    owner, doctor, other, colleague, _, recent, current, _ = _fixture(database)
    _evidence(database, recent, field="medications", value="Metformin")
    app.dependency_overrides[get_current_auth_user] = lambda: owner
    assert client.get(f"/api/sessions/{current.id}/continuity").status_code == 200
    app.dependency_overrides[get_current_auth_user] = lambda: other
    assert client.get(f"/api/sessions/{current.id}/continuity").status_code == 403
    app.dependency_overrides[get_current_auth_user] = lambda: doctor
    assert client.get(f"/api/sessions/{current.id}/continuity").status_code == 200
    app.dependency_overrides[get_current_auth_user] = lambda: colleague
    assert client.get(f"/api/sessions/{current.id}/continuity").status_code == 403
    triage = models.User(id=str(uuid.uuid4()), name="Triage", role="triage", is_active=True)
    database.add(triage)
    database.commit()
    app.dependency_overrides[get_current_auth_user] = lambda: triage
    assert client.get(f"/api/sessions/{current.id}/continuity").status_code == 403
    app.dependency_overrides.pop(get_current_auth_user, None)


def test_reconfirmation_candidate_is_stable_and_never_uses_acute_history(database):
    _, _, _, _, _, recent, current, _ = _fixture(database)
    medication = _evidence(database, recent, field="medications.details", value="Metformin 500 mg")
    _evidence(database, recent, field="chief_complaint.description", value="fever")

    first = continuity.pending_reconfirmation(database, current.id, "medications.details")
    second = continuity.pending_reconfirmation(database, current.id, "medications.details")

    assert first[0].id == medication.id
    assert first[1].evidence_id == medication.id
    assert first[1].source_session_id == recent.id
    assert second[1].model_dump() == first[1].model_dump()
    assert (
        continuity.pending_reconfirmation(database, current.id, "chief_complaint.description")
        is None
    )


def test_adaptive_injects_medication_reconfirmation_and_yes_projects_current_evidence(
    client, database
):
    session_id, state = selected(client, "headache")
    current = database.get(models.Session, session_id)
    prior = models.Session(
        id=str(uuid.uuid4()),
        patient_id=current.patient_id,
        user_id=current.user_id,
        hospital_token="C9",
        language="en",
        status="confirmed",
        completed_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    database.add(prior)
    database.flush()
    historical = _evidence(
        database, prior, field="medications.details", value="Metformin 500 mg twice daily"
    )
    database.commit()

    state = until(client, session_id, state, "medications.any")
    state = submit(client, session_id, state, True, "answered", raw_value="Yes")
    state = until(client, session_id, state, "continuity." + historical.id.replace("-", ""))
    assert state["question"]["origin"] == "continuity"
    assert state["continuity_reconfirmation"]["evidence_id"] == historical.id
    refreshed = client.get(f"/api/sessions/{session_id}/interview").json()
    assert refreshed["question"]["question_id"] == state["question"]["question_id"]

    state = submit(client, session_id, state, "yes", "answered", raw_value="Yes")
    assert state["question"]["question_id"] != "medications.details"
    evidence = (
        database.query(models.ClinicalEvidence)
        .filter(models.ClinicalEvidence.session_id == session_id)
        .all()
    )
    assert any(
        (row.metadata_json or {}).get("historical_evidence_id") == historical.id
        and (row.metadata_json or {}).get("historical_source_session_id") == prior.id
        for row in evidence
    )
    assert continuity.snapshot(database, session_id).changes.unchanged[0].status == "UNCHANGED"


def test_continuity_medication_correction_yes_to_no(client, database):
    """Append-only YES projections become non-authoritative after a NO correction."""
    session_id, state = selected(client, "headache")
    current = database.get(models.Session, session_id)
    prior = models.Session(
        id=str(uuid.uuid4()),
        patient_id=current.patient_id,
        user_id=current.user_id,
        hospital_token="C9",
        language="en",
        status="confirmed",
        completed_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    database.add(prior)
    database.flush()
    historical = _evidence(
        database, prior, field="medications.details", value="Metformin 500 mg twice daily"
    )
    database.commit()
    continuity_id = "continuity." + historical.id.replace("-", "")
    state = until(client, session_id, state, "medications.any")
    state = submit(client, session_id, state, True, "answered", raw_value="Yes")
    state = until(client, session_id, state, continuity_id)
    state = submit(client, session_id, state, "yes", "answered", raw_value="Yes")
    yes_answer = next(
        row for row in database.query(models.InterviewAnswer).all() if row.question_id == continuity_id
    )
    yes_projection = next(
        row
        for row in database.query(models.InterviewAnswer).all()
        if row.question_id == "medications.details"
    )
    answers_before = database.query(models.InterviewAnswer).count()
    evidence_before = database.query(models.ClinicalEvidence).count()
    reopened = client.put(
        f"/api/sessions/{session_id}/interview/cursor",
        json={"question_id": continuity_id, "expected_revision": state["revision"]},
    )
    assert reopened.status_code == 200
    assert reopened.json()["question"]["question_id"] == continuity_id
    assert reopened.json()["current_answer"]["value"] == "yes"
    assert client.get(f"/api/sessions/{session_id}/interview").status_code == 200
    assert database.query(models.InterviewAnswer).count() == answers_before
    assert database.query(models.ClinicalEvidence).count() == evidence_before
    state = submit(client, session_id, reopened.json(), "no", "answered", raw_value="No")
    continuity_answers = [
        row for row in database.query(models.InterviewAnswer).all() if row.question_id == continuity_id
    ]
    no_answer = continuity_answers[-1]
    assert len(continuity_answers) == 2 and yes_answer.id != no_answer.id
    assert json.loads(no_answer.value_json)["value"] == "no"
    assert database.get(models.InterviewAnswer, yes_projection.id) is not None
    authoritative = continuity.authoritative_interview_answers(database, session_id)
    assert yes_projection.id not in {row.id for row in authoritative}
    assert continuity.snapshot(database, session_id).changes.resolved[0].status == "RESOLVED"
    current_evidence = continuity.current_evidence(database, session_id)
    assert any(
        row.value_json == "no"
        and (row.metadata_json or {}).get("historical_evidence_id") == historical.id
        and (row.metadata_json or {}).get("historical_source_session_id") == prior.id
        for row in current_evidence
    )
    assert database.get(models.ClinicalEvidence, historical.id).value_json == "Metformin 500 mg twice daily"


def test_continuity_medication_correction_no_to_yes(client, database):
    session_id, state = selected(client, "headache")
    current = database.get(models.Session, session_id)
    prior = models.Session(
        id=str(uuid.uuid4()), patient_id=current.patient_id, user_id=current.user_id,
        hospital_token="C9", language="en", status="confirmed",
        completed_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    database.add(prior)
    database.flush()
    historical = _evidence(
        database, prior, field="medications.details", value="Metformin 500 mg twice daily"
    )
    database.commit()
    continuity_id = "continuity." + historical.id.replace("-", "")
    state = until(client, session_id, state, "medications.any")
    state = submit(client, session_id, state, True, "answered", raw_value="Yes")
    state = until(client, session_id, state, continuity_id)
    state = submit(client, session_id, state, "no", "answered", raw_value="No")
    no_answer = next(row for row in database.query(models.InterviewAnswer).all() if row.question_id == continuity_id)
    no_projection = next(row for row in database.query(models.InterviewAnswer).all() if row.question_id == "medications.details")
    answer_count = database.query(models.InterviewAnswer).count()
    evidence_count = database.query(models.ClinicalEvidence).count()
    reopened = client.put(f"/api/sessions/{session_id}/interview/cursor", json={"question_id": continuity_id, "expected_revision": state["revision"]})
    assert reopened.status_code == 200
    assert reopened.json()["question"]["question_id"] == continuity_id
    assert reopened.json()["current_answer"]["value"] == "no"
    assert client.get(f"/api/sessions/{session_id}/interview").status_code == 200
    assert database.query(models.InterviewAnswer).count() == answer_count
    assert database.query(models.ClinicalEvidence).count() == evidence_count
    state = submit(client, session_id, reopened.json(), "yes", "answered", raw_value="Yes")
    answers = [row for row in database.query(models.InterviewAnswer).all() if row.question_id == continuity_id]
    yes_answer = answers[-1]
    assert len(answers) == 2 and yes_answer.id != no_answer.id
    assert json.loads(yes_answer.value_json)["value"] == "yes"
    assert database.get(models.InterviewAnswer, no_projection.id) is not None
    authoritative = continuity.authoritative_interview_answers(database, session_id)
    assert no_projection.id not in {row.id for row in authoritative}
    assert continuity.snapshot(database, session_id).changes.unchanged[0].status == "UNCHANGED"
    latest = continuity.current_evidence(database, session_id)
    assert any(
        row.value_json == "Metformin 500 mg twice daily"
        and (row.metadata_json or {}).get("historical_evidence_id") == historical.id
        and (row.metadata_json or {}).get("historical_source_session_id") == prior.id
        for row in latest
    )
    rereopened = client.put(f"/api/sessions/{session_id}/interview/cursor", json={"question_id": continuity_id, "expected_revision": state["revision"]})
    assert rereopened.status_code == 200
    assert rereopened.json()["current_answer"]["value"] == "yes"
    assert database.get(models.ClinicalEvidence, historical.id).value_json == "Metformin 500 mg twice daily"


def test_continuity_medication_correction_yes_to_changed(client, database):
    session_id, state = selected(client, "headache")
    current = database.get(models.Session, session_id)
    prior = models.Session(
        id=str(uuid.uuid4()),
        patient_id=current.patient_id,
        user_id=current.user_id,
        hospital_token="C9",
        language="en",
        status="confirmed",
        completed_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    database.add(prior)
    database.flush()
    historical = _evidence(
        database, prior, field="medications.details", value="Metformin 500 mg twice daily"
    )
    database.commit()
    historical_value = historical.value_json
    continuity_id = "continuity." + historical.id.replace("-", "")

    state = until(client, session_id, state, "medications.any")
    state = submit(client, session_id, state, True, "answered", raw_value="Yes")
    state = until(client, session_id, state, continuity_id)
    state = submit(client, session_id, state, "yes", "answered", raw_value="Yes")
    yes_answer = next(
        row for row in database.query(models.InterviewAnswer).all()
        if row.question_id == continuity_id
    )
    yes_projection = next(
        row for row in database.query(models.InterviewAnswer).all()
        if row.session_id == session_id and row.question_id == "medications.details"
    )
    medication_coverage = lambda: next(
        item for item in clinical_coverage.coverage(database, session_id).fields
        if item.field == "medications.details"
    )
    assert state["question"]["question_id"] != "medications.details"
    assert medication_coverage().state == "CONFIRMED"
    assert continuity.snapshot(database, session_id).changes.unchanged[0].status == "UNCHANGED"

    reopened = client.put(
        f"/api/sessions/{session_id}/interview/cursor",
        json={"question_id": continuity_id, "expected_revision": state["revision"]},
    )
    assert reopened.status_code == 200
    assert reopened.json()["question"]["question_id"] == continuity_id
    assert reopened.json()["current_answer"]["value"] == "yes"
    state = submit(client, session_id, reopened.json(), "changed", "answered", raw_value="Changed")
    continuity_answers = [
        row for row in database.query(models.InterviewAnswer).all()
        if row.session_id == session_id and row.question_id == continuity_id
    ]
    changed_answer = continuity_answers[-1]
    assert changed_answer.id != yes_answer.id
    assert database.get(models.InterviewAnswer, yes_answer.id) is not None
    assert json.loads(changed_answer.value_json)["value"] == "changed"
    assert database.get(models.InterviewAnswer, yes_projection.id) is not None
    assert yes_projection.id not in {
        row.id for row in continuity.authoritative_interview_answers(database, session_id)
    }
    assert medication_coverage().state != "CONFIRMED"
    assert state["question"]["question_id"] == "medications.details"
    assert "medications.details" in state["missing_required"]
    changed_evidence = next(
        row for row in database.query(models.ClinicalEvidence).all()
        if row.session_id == session_id and row.source_id == changed_answer.id
    )
    assert changed_evidence.metadata_json["historical_evidence_id"] == historical.id
    assert changed_evidence.metadata_json["historical_source_session_id"] == prior.id
    assert database.get(models.ClinicalEvidence, historical.id).value_json == historical_value

    detail = "Metformin 1000 mg daily"
    state = submit(client, session_id, state, detail, "answered", raw_value=detail)
    direct_answer = next(
        row for row in database.query(models.InterviewAnswer).all()
        if row.session_id == session_id and row.question_id == "medications.details"
        and row.id != yes_projection.id
    )
    assert direct_answer.id in {
        row.id for row in continuity.authoritative_interview_answers(database, session_id)
    }
    assert any(
        row.session_id == session_id and row.source_id == direct_answer.id
        and row.value_json == detail
        for row in database.query(models.ClinicalEvidence).all()
    )
    assert state["question"]["question_id"] != "medications.details"
    assert continuity.snapshot(database, session_id).changes.changed[0].status == "CHANGED"
    assert medication_coverage().state == "CONFIRMED"
    assert yes_projection.id not in {
        row.id for row in continuity.authoritative_interview_answers(database, session_id)
    }
    assert database.get(models.ClinicalEvidence, historical.id).value_json == historical_value

    reopened = client.put(
        f"/api/sessions/{session_id}/interview/cursor",
        json={"question_id": continuity_id, "expected_revision": state["revision"]},
    )
    assert reopened.status_code == 200
    assert reopened.json()["current_answer"]["value"] == "changed"


def test_continuity_medication_correction_changed_to_yes_preserves_direct_detail(
    client, database
):
    session_id, state = selected(client, "headache")
    current = database.get(models.Session, session_id)
    prior = models.Session(
        id=str(uuid.uuid4()),
        patient_id=current.patient_id,
        user_id=current.user_id,
        hospital_token="C9",
        language="en",
        status="confirmed",
        completed_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    database.add(prior)
    database.flush()
    historical = _evidence(
        database, prior, field="medications.details", value="Metformin 500 mg twice daily"
    )
    database.commit()
    historical_value = historical.value_json
    continuity_id = "continuity." + historical.id.replace("-", "")

    state = until(client, session_id, state, "medications.any")
    state = submit(client, session_id, state, True, "answered", raw_value="Yes")
    state = until(client, session_id, state, continuity_id)
    state = submit(client, session_id, state, "changed", "answered", raw_value="Changed")
    changed_answer = next(
        row for row in database.query(models.InterviewAnswer).all()
        if row.session_id == session_id and row.question_id == continuity_id
    )
    assert state["question"]["question_id"] == "medications.details"
    detail = "Metformin 1000 mg daily"
    state = submit(client, session_id, state, detail, "answered", raw_value=detail)
    direct_answer = next(
        row for row in database.query(models.InterviewAnswer).all()
        if row.session_id == session_id and row.question_id == "medications.details"
    )
    direct_evidence = next(
        row for row in database.query(models.ClinicalEvidence).all()
        if row.session_id == session_id and row.source_id == direct_answer.id
    )
    assert continuity.snapshot(database, session_id).changes.changed[0].status == "CHANGED"

    reopened = client.put(
        f"/api/sessions/{session_id}/interview/cursor",
        json={"question_id": continuity_id, "expected_revision": state["revision"]},
    )
    assert reopened.status_code == 200
    assert reopened.json()["question"]["question_id"] == continuity_id
    assert reopened.json()["current_answer"]["value"] == "changed"
    state = submit(client, session_id, reopened.json(), "yes", "answered", raw_value="Yes")
    continuity_answers = [
        row for row in database.query(models.InterviewAnswer).all()
        if row.session_id == session_id and row.question_id == continuity_id
    ]
    yes_answer = continuity_answers[-1]
    assert yes_answer.id != changed_answer.id
    assert json.loads(yes_answer.value_json)["value"] == "yes"
    assert database.get(models.InterviewAnswer, changed_answer.id) is not None
    assert database.get(models.InterviewAnswer, direct_answer.id) is not None
    assert database.get(models.ClinicalEvidence, direct_evidence.id) is not None
    assert database.get(models.ClinicalEvidence, historical.id).value_json == historical_value

    authoritative = continuity.authoritative_interview_answers(database, session_id)
    assert direct_answer.id in {row.id for row in authoritative}
    assert yes_answer.id in {row.id for row in authoritative}
    current_rows = continuity.current_evidence(database, session_id)
    assert direct_evidence.id in {row.id for row in current_rows}
    yes_evidence = next(row for row in current_rows if row.source_id == yes_answer.id)
    assert yes_evidence.value_json == historical_value
    assert yes_evidence.metadata_json["historical_evidence_id"] == historical.id
    assert yes_evidence.metadata_json["historical_source_session_id"] == prior.id
    assert direct_evidence.source_id == direct_answer.id
    assert direct_evidence.value_json == detail
    assert not (direct_evidence.metadata_json or {}).get("confirmation_answer_id")
    assert all(
        not (row.metadata_json or {}).get("confirmation_answer_id")
        or (row.metadata_json or {})["confirmation_answer_id"] == yes_answer.id
        for row in current_rows
    )

    # Both attributable current values survive. The later YES answer supplies
    # the comparison value, while the direct changed detail remains visible.
    changes = continuity.snapshot(database, session_id).changes
    item = next(
        item for item in changes.unchanged
        if item.canonical_field == "medications.details"
    )
    assert item.status == "UNCHANGED"
    assert {direct_evidence.id, yes_evidence.id} <= {
        ref.evidence_id for ref in item.current_evidence_refs
    }
    yes_projection_evidence = next(
        row for row in current_rows
        if (row.metadata_json or {}).get("confirmation_answer_id") == yes_answer.id
    )
    yes_projection = database.get(models.InterviewAnswer, yes_projection_evidence.source_id)
    assert yes_projection is not None
    assert yes_projection.id in {row.id for row in authoritative}
    coverage_field = next(
        item for item in clinical_coverage.coverage(database, session_id).fields
        if item.field == "medications.details"
    )
    assert coverage_field.state == "CONFIRMED"
    # Coverage's established latest-by-field rule selects the later YES
    # projection; the conflicting direct detail stays attributable and active.
    assert coverage_field.patient_answer_id == yes_projection.id
    assert database.get(models.InterviewAnswer, direct_answer.id) is not None
    assert database.get(models.ClinicalEvidence, direct_evidence.id) is not None
    assert database.get(models.ClinicalEvidence, historical.id).value_json == historical_value

    rereopened = client.put(
        f"/api/sessions/{session_id}/interview/cursor",
        json={"question_id": continuity_id, "expected_revision": state["revision"]},
    )
    assert rereopened.status_code == 200
    assert rereopened.json()["current_answer"]["value"] == "yes"


def test_continuity_medication_correction_not_sure_to_yes(client, database):
    session_id, state = selected(client, "headache")
    current = database.get(models.Session, session_id)
    prior = models.Session(
        id=str(uuid.uuid4()),
        patient_id=current.patient_id,
        user_id=current.user_id,
        hospital_token="C9",
        language="en",
        status="confirmed",
        completed_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    database.add(prior)
    database.flush()
    historical = _evidence(
        database, prior, field="medications.details", value="Metformin 500 mg twice daily"
    )
    database.commit()
    historical_value = historical.value_json
    continuity_id = "continuity." + historical.id.replace("-", "")

    state = until(client, session_id, state, "medications.any")
    state = submit(client, session_id, state, True, "answered", raw_value="Yes")
    parent_answer = next(
        row for row in database.query(models.InterviewAnswer).all()
        if row.session_id == session_id and row.question_id == "medications.any"
    )
    state = until(client, session_id, state, continuity_id)
    state = submit(client, session_id, state, "not_sure", "answered", raw_value="Not sure")
    not_sure_answer = next(
        row for row in database.query(models.InterviewAnswer).all()
        if row.session_id == session_id and row.question_id == continuity_id
    )
    assert not_sure_answer.session_id == session_id
    uncertainty_evidence = next(
        row for row in database.query(models.ClinicalEvidence).all()
        if row.session_id == session_id and row.source_id == not_sure_answer.id
    )
    assert uncertainty_evidence.metadata_json["historical_evidence_id"] == historical.id
    assert uncertainty_evidence.metadata_json["historical_source_session_id"] == prior.id
    assert continuity.snapshot(database, session_id).changes.unknown_current_status[0].status == (
        "UNKNOWN_CURRENT_STATUS"
    )
    coverage_field = lambda: next(
        item for item in clinical_coverage.coverage(database, session_id).fields
        if item.field == "medications.details"
    )
    assert coverage_field().state != "CONFIRMED"
    assert not any(
        row.question_id == "medications.details"
        for row in continuity.authoritative_interview_answers(database, session_id)
    )
    assert database.get(models.ClinicalEvidence, historical.id).value_json == historical_value

    answer_count = database.query(models.InterviewAnswer).count()
    evidence_count = database.query(models.ClinicalEvidence).count()
    reopened = client.put(
        f"/api/sessions/{session_id}/interview/cursor",
        json={"question_id": continuity_id, "expected_revision": state["revision"]},
    )
    assert reopened.status_code == 200
    assert reopened.json()["question"]["question_id"] == continuity_id
    assert reopened.json()["current_answer"]["value"] == "not_sure"
    assert client.get(f"/api/sessions/{session_id}/interview").json()["current_answer"]["value"] == "not_sure"
    assert database.query(models.InterviewAnswer).count() == answer_count
    assert database.query(models.ClinicalEvidence).count() == evidence_count

    state = submit(client, session_id, reopened.json(), "yes", "answered", raw_value="Yes")
    answers = [
        row for row in database.query(models.InterviewAnswer).all()
        if row.session_id == session_id and row.question_id == continuity_id
    ]
    yes_answer = answers[-1]
    assert len(answers) == 2 and yes_answer.id != not_sure_answer.id
    assert json.loads(yes_answer.value_json)["value"] == "yes"
    assert database.get(models.InterviewAnswer, not_sure_answer.id) is not None
    assert database.get(models.ClinicalEvidence, uncertainty_evidence.id) is not None
    authoritative = continuity.authoritative_interview_answers(database, session_id)
    assert parent_answer.id in {row.id for row in authoritative}
    assert yes_answer.id in {row.id for row in authoritative}
    yes_projection_evidence = next(
        row for row in continuity.current_evidence(database, session_id)
        if (row.metadata_json or {}).get("confirmation_answer_id") == yes_answer.id
    )
    assert yes_projection_evidence.source_id in {row.id for row in authoritative}
    assert uncertainty_evidence.id not in {
        row.id for row in continuity.current_evidence(database, session_id)
    }
    yes_evidence = next(
        row for row in continuity.current_evidence(database, session_id)
        if row.source_id == yes_answer.id
    )
    assert yes_evidence.value_json == historical_value
    assert yes_evidence.metadata_json["historical_evidence_id"] == historical.id
    assert yes_evidence.metadata_json["historical_source_session_id"] == prior.id
    item = next(
        item for item in continuity.snapshot(database, session_id).changes.unchanged
        if item.canonical_field == "medications.details"
    )
    assert item.current_value == historical_value
    assert yes_evidence.id in {ref.evidence_id for ref in item.current_evidence_refs}
    assert coverage_field().state == "CONFIRMED"
    assert database.get(models.ClinicalEvidence, historical.id).value_json == historical_value

    reopened = client.put(
        f"/api/sessions/{session_id}/interview/cursor",
        json={"question_id": continuity_id, "expected_revision": state["revision"]},
    )
    assert reopened.status_code == 200
    assert reopened.json()["current_answer"]["value"] == "yes"


def test_continuity_allergy_correction_yes_to_no(client, database):
    session_id, state = selected(client, "headache")
    current = database.get(models.Session, session_id)
    prior = models.Session(
        id=str(uuid.uuid4()),
        patient_id=current.patient_id,
        user_id=current.user_id,
        hospital_token="C9",
        language="en",
        status="confirmed",
        completed_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    database.add(prior)
    database.flush()
    historical = _evidence(database, prior, field="allergies.details", value="Penicillin")
    database.commit()
    historical_value = historical.value_json
    continuity_id = "continuity." + historical.id.replace("-", "")

    state = until(client, session_id, state, "allergies.any")
    state = submit(client, session_id, state, True, "answered", raw_value="Yes")
    state = until(client, session_id, state, continuity_id)
    state = submit(client, session_id, state, "yes", "answered", raw_value="Yes")
    yes_answer = next(
        row for row in database.query(models.InterviewAnswer).all()
        if row.session_id == session_id and row.question_id == continuity_id
    )
    yes_projection = next(
        row for row in database.query(models.InterviewAnswer).all()
        if row.session_id == session_id and row.question_id == "allergies.details"
    )
    assert continuity.snapshot(database, session_id).changes.unchanged[0].status == "UNCHANGED"

    answer_count = database.query(models.InterviewAnswer).count()
    evidence_count = database.query(models.ClinicalEvidence).count()
    reopened = client.put(
        f"/api/sessions/{session_id}/interview/cursor",
        json={"question_id": continuity_id, "expected_revision": state["revision"]},
    )
    assert reopened.status_code == 200
    assert reopened.json()["question"]["question_id"] == continuity_id
    assert reopened.json()["current_answer"]["value"] == "yes"
    assert client.get(f"/api/sessions/{session_id}/interview").json()["current_answer"]["value"] == "yes"
    assert database.query(models.InterviewAnswer).count() == answer_count
    assert database.query(models.ClinicalEvidence).count() == evidence_count

    state = submit(client, session_id, reopened.json(), "no", "answered", raw_value="No")
    answers = [
        row for row in database.query(models.InterviewAnswer).all()
        if row.session_id == session_id and row.question_id == continuity_id
    ]
    no_answer = answers[-1]
    assert len(answers) == 2 and yes_answer.id != no_answer.id
    assert json.loads(no_answer.value_json)["value"] == "no"
    assert database.get(models.InterviewAnswer, yes_answer.id) is not None
    assert database.get(models.InterviewAnswer, yes_projection.id) is not None
    authoritative = continuity.authoritative_interview_answers(database, session_id)
    assert yes_projection.id not in {row.id for row in authoritative}
    no_projection_evidence = next(
        row for row in continuity.current_evidence(database, session_id)
        if (row.metadata_json or {}).get("confirmation_answer_id") == no_answer.id
    )
    assert no_projection_evidence.value_json == "no"
    assert no_projection_evidence.source_id in {row.id for row in authoritative}
    no_evidence = next(
        row for row in continuity.current_evidence(database, session_id)
        if row.source_id == no_answer.id
    )
    assert no_evidence.metadata_json["historical_evidence_id"] == historical.id
    assert no_evidence.metadata_json["historical_source_session_id"] == prior.id
    conflict = next(
        item for item in continuity.snapshot(database, session_id).changes.conflicted
        if item.canonical_field == "allergies.details"
    )
    assert {historical.id} <= {ref.evidence_id for ref in conflict.historical_evidence_refs}
    assert {no_evidence.id, no_projection_evidence.id} <= {
        ref.evidence_id for ref in conflict.current_evidence_refs
    }
    coverage_field = next(
        item for item in clinical_coverage.coverage(database, session_id).fields
        if item.field == "allergies.details"
    )
    assert coverage_field.state == "CONFIRMED"
    assert coverage_field.patient_answer_id == no_projection_evidence.source_id
    assert database.get(models.ClinicalEvidence, historical.id).value_json == historical_value

    reopened = client.put(
        f"/api/sessions/{session_id}/interview/cursor",
        json={"question_id": continuity_id, "expected_revision": state["revision"]},
    )
    assert reopened.status_code == 200
    assert reopened.json()["current_answer"]["value"] == "no"


def test_continuity_allergy_correction_no_to_yes(client, database):
    session_id, state = selected(client, "headache")
    current = database.get(models.Session, session_id)
    prior = models.Session(
        id=str(uuid.uuid4()),
        patient_id=current.patient_id,
        user_id=current.user_id,
        hospital_token="C9",
        language="en",
        status="confirmed",
        completed_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    database.add(prior)
    database.flush()
    historical = _evidence(database, prior, field="allergies.details", value="Penicillin")
    database.commit()
    historical_value = historical.value_json
    continuity_id = "continuity." + historical.id.replace("-", "")

    state = until(client, session_id, state, "allergies.any")
    state = submit(client, session_id, state, True, "answered", raw_value="Yes")
    state = until(client, session_id, state, continuity_id)
    state = submit(client, session_id, state, "no", "answered", raw_value="No")
    no_answer = next(
        row for row in database.query(models.InterviewAnswer).all()
        if row.session_id == session_id and row.question_id == continuity_id
    )
    no_projection = next(
        row for row in database.query(models.InterviewAnswer).all()
        if row.session_id == session_id and row.question_id == "allergies.details"
    )
    assert continuity.snapshot(database, session_id).changes.conflicted[0].status == "CONFLICTED"
    coverage_field = lambda: next(
        item for item in clinical_coverage.coverage(database, session_id).fields
        if item.field == "allergies.details"
    )
    assert coverage_field().state == "CONFIRMED"
    assert coverage_field().patient_answer_id == no_projection.id

    answer_count = database.query(models.InterviewAnswer).count()
    evidence_count = database.query(models.ClinicalEvidence).count()
    reopened = client.put(
        f"/api/sessions/{session_id}/interview/cursor",
        json={"question_id": continuity_id, "expected_revision": state["revision"]},
    )
    assert reopened.status_code == 200
    assert reopened.json()["question"]["question_id"] == continuity_id
    assert reopened.json()["current_answer"]["value"] == "no"
    for _ in range(2):
        refreshed = client.get(f"/api/sessions/{session_id}/interview")
        assert refreshed.status_code == 200
        assert refreshed.json()["current_answer"]["value"] == "no"
    assert database.query(models.InterviewAnswer).count() == answer_count
    assert database.query(models.ClinicalEvidence).count() == evidence_count

    state = submit(client, session_id, reopened.json(), "yes", "answered", raw_value="Yes")
    answers = [
        row for row in database.query(models.InterviewAnswer).all()
        if row.session_id == session_id and row.question_id == continuity_id
    ]
    yes_answer = answers[-1]
    assert len(answers) == 2 and yes_answer.id != no_answer.id
    assert json.loads(yes_answer.value_json)["value"] == "yes"
    assert database.get(models.InterviewAnswer, no_answer.id) is not None
    assert database.get(models.InterviewAnswer, no_projection.id) is not None
    authoritative = continuity.authoritative_interview_answers(database, session_id)
    assert no_projection.id not in {row.id for row in authoritative}
    yes_projection_evidence = next(
        row for row in continuity.current_evidence(database, session_id)
        if (row.metadata_json or {}).get("confirmation_answer_id") == yes_answer.id
    )
    assert yes_projection_evidence.value_json == historical_value
    assert yes_projection_evidence.source_id in {row.id for row in authoritative}
    yes_evidence = next(
        row for row in continuity.current_evidence(database, session_id)
        if row.source_id == yes_answer.id
    )
    assert yes_evidence.value_json == historical_value
    assert yes_evidence.metadata_json["historical_evidence_id"] == historical.id
    assert yes_evidence.metadata_json["historical_source_session_id"] == prior.id
    assert all(row.source_id != no_answer.id for row in continuity.current_evidence(database, session_id))
    item = next(
        item for item in continuity.snapshot(database, session_id).changes.unchanged
        if item.canonical_field == "allergies.details"
    )
    assert historical.id in {ref.evidence_id for ref in item.historical_evidence_refs}
    assert yes_evidence.id in {ref.evidence_id for ref in item.current_evidence_refs}
    assert coverage_field().state == "CONFIRMED"
    assert coverage_field().patient_answer_id == yes_projection_evidence.source_id
    assert database.get(models.ClinicalEvidence, historical.id).value_json == historical_value

    rereopened = client.put(
        f"/api/sessions/{session_id}/interview/cursor",
        json={"question_id": continuity_id, "expected_revision": state["revision"]},
    )
    assert rereopened.status_code == 200
    assert rereopened.json()["current_answer"]["value"] == "yes"


@pytest.mark.parametrize(
    "case",
    [
        "malformed",
        "truncated",
        "unknown_uuid",
        "other_patient",
        "current_session",
        "incomplete_prior",
        "unsupported_field",
        "ineligible_evidence",
        "unsupported_medication_parent",
    ],
)
def test_continuity_cursor_rejects_invalid_or_ineligible_evidence(client, database, case):
    session_id, state = selected(client, "headache")
    current = database.get(models.Session, session_id)
    secret = "OtherPatientSecretPenicillin"
    source_session_id = None
    if case == "malformed":
        question_id = "continuity.not-a-uuid"
    elif case == "truncated":
        question_id = "continuity." + uuid.uuid4().hex[:20]
    elif case == "unknown_uuid":
        question_id = "continuity." + uuid.uuid4().hex
    else:
        if case == "other_patient":
            patient = models.Patient(id=str(uuid.uuid4()), name="Other Patient Secret")
            database.add(patient)
            database.flush()
        else:
            patient = database.get(models.Patient, current.patient_id)
        if case == "current_session":
            source = current
        else:
            source = _session(
                database,
                patient,
                status="intake" if case == "incomplete_prior" else "confirmed",
                completed_at=None if case == "incomplete_prior" else datetime.now(timezone.utc),
            )
        source_session_id = source.id
        field = (
            "hpi.onset" if case == "unsupported_field" else
            "medications.any" if case == "unsupported_medication_parent" else
            "allergies.details" if case == "other_patient" else "medications.details"
        )
        value = secret if case == "other_patient" else "Private historical medication"
        evidence = _evidence(database, source, field=field, value=value)
        if case == "ineligible_evidence":
            evidence.verification_status = "REJECTED"
        question_id = continuity.continuity_question_id(evidence.id)
        database.commit()

    assert continuity.reconfirmation_context_for_question(database, session_id, question_id) is None
    answer_count = database.query(models.InterviewAnswer).count()
    evidence_count = database.query(models.ClinicalEvidence).count()
    audit_count = database.query(models.AuditLog).count()
    original_cursor = database.get(models.InterviewRun, session_id).cursor
    response = client.put(
        f"/api/sessions/{session_id}/interview/cursor",
        json={"question_id": question_id, "expected_revision": state["revision"]},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "QUESTION_NOT_ACTIVE"
    body = response.text
    assert secret not in body
    assert "Private historical medication" not in body
    assert "Other Patient Secret" not in body
    if source_session_id is not None:
        assert source_session_id not in body
    resumed = client.get(f"/api/sessions/{session_id}/interview")
    assert resumed.status_code == 200
    assert resumed.json()["question"]["question_id"] == original_cursor
    assert database.get(models.InterviewRun, session_id).cursor == original_cursor
    assert database.query(models.InterviewAnswer).count() == answer_count
    assert database.query(models.ClinicalEvidence).count() == evidence_count
    assert database.query(models.AuditLog).count() == audit_count


def test_continuity_cursor_resolver_accepts_eligible_same_patient_detail(database):
    _, _, _, _, _, prior, current, _ = _fixture(database)
    historical = _evidence(
        database, prior, field="medications.details", value="Metformin 500 mg twice daily"
    )
    question_id = continuity.continuity_question_id(historical.id)
    resolved = continuity.reconfirmation_context_for_question(database, current.id, question_id)
    assert resolved is not None
    assert resolved[0].id == historical.id
    assert resolved[1].source_session_id == prior.id
