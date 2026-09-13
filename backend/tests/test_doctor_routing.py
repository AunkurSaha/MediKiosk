from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app import models
from app.api.deps import require_patient
from app.core import security
from app.main import app
from app.services import doctor_routing


def patient(database, suffix="a"):
    user = models.User(
        id=str(uuid4()),
        name=f"Patient {suffix}",
        phone_number=f"+9190000000{suffix}",
        role="patient",
        is_active=True,
    )
    database.add(user)
    database.commit()
    return user


def session_for(database, user, hospital=None, doctor=None):
    person = models.Patient(name=user.name)
    database.add(person)
    database.flush()
    visit = models.Session(
        id=str(uuid4()),
        patient_id=person.id,
        user_id=user.id,
        hospital_token=str(uuid4()),
        language="en",
        status="intake",
        hospital_id=hospital,
        selected_doctor_id=doctor,
    )
    database.add(visit)
    database.commit()
    return visit


def doctor(database, name, hospital_id, specialty="CARDIOLOGY", *, active=True, accepting=True):
    user = models.User(
        id=str(uuid4()),
        name=name,
        email=f"{uuid4()}@tests.invalid",
        role="doctor",
        is_active=active,
    )
    database.add(user)
    database.flush()
    database.add(
        models.DoctorProfile(
            doctor_user_id=user.id, display_name=name, active=active, accepting_patients=accepting
        )
    )
    database.flush()
    database.add(
        models.DoctorHospitalMembership(doctor_id=user.id, hospital_id=hospital_id, active=True)
    )
    database.add(models.DoctorSpecialtyMembership(doctor_id=user.id, specialty_code=specialty))
    database.commit()
    return user


def choose_patient(client, user):
    app.dependency_overrides[require_patient] = lambda: user


def auth_headers(database, user):
    raw, token_hash = security.generate_session_token()
    database.add(
        models.AuthSession(
            session_token_hash=token_hash,
            user_id=user.id,
            role=user.role,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            is_revoked=False,
        )
    )
    database.commit()
    return {"Authorization": f"Bearer {raw}"}


def test_hospital_selection_and_ownership(client, database):
    active = models.Hospital(id=str(uuid4()), code="ACTIVE", name="Active Hospital", active=True)
    inactive = models.Hospital(
        id=str(uuid4()), code="INACTIVE", name="Inactive Hospital", active=False
    )
    database.add_all([active, inactive])
    database.commit()
    first, second = patient(database, "11"), patient(database, "12")
    visit = session_for(database, first)
    listed = client.get("/api/hospitals")
    assert listed.status_code == 200
    assert active.id in {item["id"] for item in listed.json()["items"]}
    assert inactive.id not in {item["id"] for item in listed.json()["items"]}
    choose_patient(client, first)
    assert (
        client.put(
            f"/api/sessions/{visit.id}/hospital", json={"hospital_id": active.id}
        ).status_code
        == 200
    )
    assert (
        client.put(
            f"/api/sessions/{visit.id}/hospital", json={"hospital_id": inactive.id}
        ).status_code
        == 422
    )
    choose_patient(client, second)
    assert (
        client.put(
            f"/api/sessions/{visit.id}/hospital", json={"hospital_id": active.id}
        ).status_code
        == 403
    )


def test_matching_filters_sorts_and_counts_waiting_only(client, database):
    hospital = models.Hospital(id=str(uuid4()), code="MATCH", name="Match Hospital", active=True)
    other_hospital = models.Hospital(
        id=str(uuid4()), code="OTHER", name="Other Hospital", active=True
    )
    database.add_all([hospital, other_hospital])
    database.commit()
    user = patient(database, "21")
    visit = session_for(database, user, hospital.id)
    database.add(
        models.InterviewRun(
            session_id=visit.id,
            flow_id="chest_pain",
            flow_version="1",
            flow_snapshot={},
            revision=0,
        )
    )
    database.commit()
    low = doctor(database, "Dr A", hospital.id)
    high = doctor(database, "Dr B", hospital.id)
    doctor(database, "Wrong Specialty", hospital.id, "NEUROLOGY")
    doctor(database, "Wrong Hospital", other_hospital.id)
    doctor(database, "Inactive", hospital.id, active=False)
    doctor(database, "Not Accepting", hospital.id, accepting=False)
    for target, statuses in (
        (low, ["WAITING", "COMPLETED", "CANCELLED"]),
        (high, ["WAITING", "WAITING"]),
    ):
        for status in statuses:
            queued_visit = session_for(
                database, patient(database, str(uuid4())[-2:]), hospital.id, target.id
            )
            database.add(
                models.DoctorQueueEntry(
                    session_id=queued_visit.id,
                    doctor_id=target.id,
                    hospital_id=hospital.id,
                    status=status,
                )
            )
    database.commit()
    choose_patient(client, user)
    response = client.get(f"/api/sessions/{visit.id}/doctors")
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [item["doctor_id"] for item in items] == [low.id, high.id]
    assert [item["waiting_count"] for item in items] == [1, 2]
    assert items[0]["recommended"] is True


def test_assignment_revalidation_queue_uniqueness_and_doctor_isolation(client, database):
    hospital = models.Hospital(id=str(uuid4()), code="SECURE", name="Secure Hospital", active=True)
    other = models.Hospital(
        id=str(uuid4()), code="SECURE2", name="Other Secure Hospital", active=True
    )
    database.add_all([hospital, other])
    database.commit()
    owner, stranger = patient(database, "31"), patient(database, "32")
    visit = session_for(database, owner, hospital.id)
    database.add(
        models.InterviewRun(
            session_id=visit.id,
            flow_id="chest_pain",
            flow_version="1",
            flow_snapshot={},
            revision=0,
        )
    )
    database.commit()
    eligible = doctor(database, "Assigned", hospital.id)
    same_hospital = doctor(database, "Not Assigned", hospital.id)
    wrong_hospital = doctor(database, "Wrong Hospital", other.id)
    wrong_specialty = doctor(database, "Wrong Specialty", hospital.id, "NEUROLOGY")
    choose_patient(client, stranger)
    assert (
        client.put(f"/api/sessions/{visit.id}/doctor", json={"doctor_id": eligible.id}).status_code
        == 403
    )
    choose_patient(client, owner)
    for invalid in (wrong_hospital, wrong_specialty):
        assert (
            client.put(
                f"/api/sessions/{visit.id}/doctor", json={"doctor_id": invalid.id}
            ).status_code
            == 422
        )
    assert (
        client.put(f"/api/sessions/{visit.id}/doctor", json={"doctor_id": eligible.id}).status_code
        == 200
    )
    assert (
        client.put(
            f"/api/sessions/{visit.id}/doctor", json={"doctor_id": same_hospital.id}
        ).status_code
        == 200
    )
    database.refresh(visit)
    assert visit.selected_doctor_id == same_hospital.id
    doctor_routing.enqueue_completed_session(database, visit)
    doctor_routing.enqueue_completed_session(database, visit)
    database.commit()
    assert (
        len(
            database.scalars(
                select(models.DoctorQueueEntry).where(
                    models.DoctorQueueEntry.session_id == visit.id
                )
            ).all()
        )
        == 1
    )
    with pytest.raises(Exception):
        doctor_routing.require_assigned_doctor(database, visit, eligible)
    doctor_routing.require_assigned_doctor(database, visit, same_hospital)


def test_only_selected_doctor_can_list_view_and_transition_queue(client, database):
    hospital = models.Hospital(
        id=str(uuid4()), code="WORKSPACE", name="Workspace Hospital", active=True
    )
    database.add(hospital)
    database.commit()
    owner = patient(database, "41")
    selected = doctor(database, "Selected Doctor", hospital.id)
    colleague = doctor(database, "Same Hospital Colleague", hospital.id)
    visit = session_for(database, owner, hospital.id, selected.id)
    visit.status = "ready_for_review"
    database.add(
        models.Consent(
            session_id=visit.id,
            share_with_doctor=True,
            voice_processing=False,
            document_processing=False,
        )
    )
    database.add(
        models.DoctorQueueEntry(
            session_id=visit.id, doctor_id=selected.id, hospital_id=hospital.id, status="WAITING"
        )
    )
    database.commit()
    selected_headers = auth_headers(database, selected)
    colleague_headers = auth_headers(database, colleague)
    patient_headers = auth_headers(database, owner)
    listing = client.get("/api/doctor/sessions", headers=selected_headers)
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()["items"]] == [visit.id]
    assert (
        client.get(f"/api/doctor/sessions/{visit.id}", headers=selected_headers).status_code == 200
    )
    assert (
        client.get(f"/api/doctor/sessions/{visit.id}", headers=colleague_headers).status_code == 403
    )
    assert client.get("/api/doctor/sessions", headers=patient_headers).status_code == 403
    assert (
        client.put(
            f"/api/doctor/sessions/{visit.id}/queue",
            headers=colleague_headers,
            json={"status": "IN_CONSULTATION"},
        ).status_code
        == 403
    )
    assert (
        client.put(
            f"/api/doctor/sessions/{visit.id}/queue",
            headers=selected_headers,
            json={"status": "IN_CONSULTATION"},
        ).status_code
        == 200
    )
    assert (
        client.put(
            f"/api/doctor/sessions/{visit.id}/queue",
            headers=selected_headers,
            json={"status": "COMPLETED"},
        ).status_code
        == 200
    )
    database.refresh(visit)
    assert (
        database.scalar(
            select(models.DoctorQueueEntry.status).where(
                models.DoctorQueueEntry.session_id == visit.id
            )
        )
        == "COMPLETED"
    )
