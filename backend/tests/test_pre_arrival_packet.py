import hashlib
import uuid

import pytest

from app import models, schemas
from app.core.errors import WorkflowError
from app.services import pre_arrival_packet


def _fixture(database):
    suffix = uuid.uuid4().hex[:8]
    hospital = models.Hospital(code=f"P8-{suffix}", name="Phase 8 Hospital")
    patient_user = models.User(
        id=str(uuid.uuid4()), name="Packet Patient", role="patient", is_active=True
    )
    patient = models.Patient(id=str(uuid.uuid4()), name="Packet Patient")
    doctor = models.User(id=str(uuid.uuid4()), name="Packet Doctor", role="doctor", is_active=True)
    triage = models.User(id=str(uuid.uuid4()), name="Packet Triage", role="triage", is_active=True)
    database.add_all([hospital, patient_user, patient, doctor, triage])
    database.flush()
    database.add(models.DoctorProfile(doctor_user_id=doctor.id, display_name=doctor.name))
    database.flush()
    database.add(
        models.DoctorHospitalMembership(doctor_id=doctor.id, hospital_id=hospital.id, active=True)
    )
    session = models.Session(
        id=str(uuid.uuid4()),
        patient_id=patient.id,
        user_id=patient_user.id,
        hospital_id=hospital.id,
        selected_doctor_id=doctor.id,
        hospital_token="P8-001",
        language="en",
        status="ready_for_review",
    )
    database.add(session)
    database.commit()
    return session, patient_user, doctor, triage


def _snapshot(session_id):
    return schemas.PreArrivalPacket(
        packet_reference=f"mkp:{session_id}",
        visit_context={"session_id": session_id},
        clinical_summary_id=str(uuid.uuid4()),
        clinical_summary_status="draft",
    )


def test_packet_is_idempotent_and_token_is_hashed_rotated_and_revocable(database, monkeypatch):
    session, patient, doctor, triage = _fixture(database)
    monkeypatch.setattr(
        pre_arrival_packet.intake,
        "build_pre_arrival_packet",
        lambda _db, session_id: _snapshot(session_id),
    )

    first = pre_arrival_packet.get_or_create(database, session.id, patient)
    second = pre_arrival_packet.get_or_create(database, session.id, patient)
    assert first.packet_id == second.packet_id

    issued = pre_arrival_packet.issue_token(database, session.id, patient)
    record = database.get(models.PreArrivalPacketRecord, first.packet_id)
    assert (
        record.handoff_token_hash
        == hashlib.sha256(issued.handoff_token.encode("utf-8")).hexdigest()
    )
    assert issued.handoff_token not in str(record.snapshot_json)
    assert (
        pre_arrival_packet.resolve(database, issued.handoff_token, None).status == "AUTH_REQUIRED"
    )
    with pytest.raises(WorkflowError) as forbidden:
        pre_arrival_packet.resolve(database, issued.handoff_token, triage)
    assert forbidden.value.code == "FORBIDDEN"

    view = pre_arrival_packet.resolve(database, issued.handoff_token, doctor)
    assert view.snapshot["visit_context"]["session_id"] == session.id

    rotated = pre_arrival_packet.issue_token(database, session.id, patient)
    assert rotated.handoff_token != issued.handoff_token
    with pytest.raises(WorkflowError) as old_link:
        pre_arrival_packet.resolve(database, issued.handoff_token, doctor)
    assert old_link.value.code == "PACKET_NOT_FOUND"

    pre_arrival_packet.revoke(database, session.id, patient)
    with pytest.raises(WorkflowError) as revoked:
        pre_arrival_packet.resolve(database, rotated.handoff_token, doctor)
    assert revoked.value.code == "PACKET_REVOKED"


def test_packet_requires_patient_owner_and_completed_assignment(database, monkeypatch):
    session, patient, doctor, _ = _fixture(database)
    monkeypatch.setattr(
        pre_arrival_packet.intake,
        "build_pre_arrival_packet",
        lambda _db, session_id: _snapshot(session_id),
    )
    with pytest.raises(WorkflowError) as staff:
        pre_arrival_packet.get_or_create(database, session.id, doctor)
    assert staff.value.code == "FORBIDDEN"
    session.status = "intake"
    database.commit()
    with pytest.raises(WorkflowError) as incomplete:
        pre_arrival_packet.get_or_create(database, session.id, patient)
    assert incomplete.value.code == "PACKET_NOT_READY"
