from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app import models
from app.api.deps import require_patient_or_demo
from app.core import security
from app.main import app
from app.services import doctor_routing, intake


def patient(database, suffix="a"):
    unique_phone = f"+91{str(uuid4().int)[-10:]}"
    user = models.User(
        id=str(uuid4()),
        name=f"Patient {suffix}",
        phone_number=unique_phone,
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
    app.dependency_overrides[require_patient_or_demo] = lambda: user


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


def test_demo_fixtures_seed_five_doctors_and_visible_patient_load_per_hospital(client, database):
    response = client.get("/api/hospitals")
    assert response.status_code == 200
    # Re-seeding is part of every local startup and must remain idempotent.
    doctor_routing.ensure_demo_routing_data(database)

    for hospital_id in (
        doctor_routing.DEMO_HOSPITAL_A,
        doctor_routing.DEMO_HOSPITAL_B,
    ):
        doctor_count = database.scalar(
            select(func.count(models.DoctorHospitalMembership.id)).where(
                models.DoctorHospitalMembership.hospital_id == hospital_id,
                models.DoctorHospitalMembership.active.is_(True),
            )
        )
        assert doctor_count == 5

        patient_load = database.scalar(
            select(func.count(models.DoctorQueueEntry.id)).where(
                models.DoctorQueueEntry.hospital_id == hospital_id,
                models.DoctorQueueEntry.status == "WAITING",
            )
        )
        assert patient_load == 15
        roster = client.get(f"/api/hospitals/{hospital_id}/doctors")
        assert roster.status_code == 200, roster.text
        assert len(roster.json()["items"]) == 5
        assert sum(item["waiting_count"] for item in roster.json()["items"]) == 15

    seeded_session_ids = database.scalars(
        select(models.DoctorQueueEntry.session_id).where(
            models.DoctorQueueEntry.hospital_id.in_(
                [doctor_routing.DEMO_HOSPITAL_A, doctor_routing.DEMO_HOSPITAL_B]
            ),
            models.DoctorQueueEntry.status == "WAITING",
        )
    ).all()
    consent_count = database.scalar(
        select(func.count(models.Consent.session_id)).where(
            models.Consent.session_id.in_(seeded_session_ids),
            models.Consent.share_with_doctor.is_(True),
        )
    )
    assert consent_count == 30

    seeded_answers = database.execute(
        select(
            models.InterviewAnswer.field,
            models.InterviewAnswer.raw_value,
            models.InterviewAnswer.language,
        ).where(models.InterviewAnswer.session_id.in_(seeded_session_ids))
    ).all()
    for field in ("chief_complaint", "onset_duration", "medications", "allergies", "past_history"):
        values = {
            raw_value for answer_field, raw_value, _ in seeded_answers if answer_field == field
        }
        assert len(values) >= 5
    assert {language for _, _, language in seeded_answers} == {"en", "bn", "hi"}

    triage_user = database.scalar(select(models.User).where(models.User.role == "triage"))
    triage_headers = auth_headers(database, triage_user)
    hospital_queues = []
    for hospital_id in (
        doctor_routing.DEMO_HOSPITAL_A,
        doctor_routing.DEMO_HOSPITAL_B,
    ):
        queue_response = client.get(
            f"/api/triage/queue?hospital_id={hospital_id}", headers=triage_headers
        )
        assert queue_response.status_code == 200, queue_response.text
        assert len(queue_response.json()["items"]) == 15
        assert {item["hospital_id"] for item in queue_response.json()["items"]} == {hospital_id}
        hospital_queues.append({item["id"] for item in queue_response.json()["items"]})
    assert hospital_queues[0].isdisjoint(hospital_queues[1])

    for (
        _,
        name,
        phone_number,
        _,
        hospital_id,
        specialties,
        queue_count,
    ) in doctor_routing.DEMO_DOCTORS:
        login = client.post(
            "/api/auth/staff-login",
            json={
                "identifier": phone_number,
                "password": doctor_routing.DEMO_DOCTOR_PASSWORD,
                "hospital_id": hospital_id,
                "specialty": specialties[0],
            },
        )
        assert login.status_code == 200, f"{name}: {login.text}"
        assert login.json()["user"]["name"] == name

        listing = client.get("/api/doctor/sessions")
        assert listing.status_code == 200, f"{name}: {listing.text}"
        active_visits = [
            item for item in listing.json()["items"] if item["queue_status"] == "WAITING"
        ]
        assert len(active_visits) == queue_count
        for item in active_visits:
            UUID(item["id"])
            detail = client.get(f"/api/doctor/sessions/{item['id']}")
            assert detail.status_code == 200, f"{name}: {detail.text}"
            record = detail.json()
            assert len(record["answers"]) == 5
            assert record["summary"]["status"] == "generated"
            assert "Patient reports" in record["summary"]["generated_text"]


def test_completed_demo_seed_is_cached_for_the_database_binding(database, monkeypatch):
    doctor_routing.ensure_demo_routing_data(database)
    calls = 0
    original_scalar = database.scalar

    def counting_scalar(statement, *args, **kwargs):
        nonlocal calls
        calls += 1
        return original_scalar(statement, *args, **kwargs)

    monkeypatch.setattr(database, "scalar", counting_scalar)
    doctor_routing.ensure_demo_routing_data(database)
    assert calls == 0


def test_demo_seed_upgrades_legacy_queue_ids_without_collisions(database):
    database.add_all(
        [
            models.Hospital(
                id=doctor_routing.DEMO_HOSPITAL_A,
                code="DEMO-KOL-01",
                name="MediKiosk City Hospital",
                active=True,
            ),
            models.Hospital(
                id=doctor_routing.DEMO_HOSPITAL_B,
                code="DEMO-KOL-02",
                name="MediKiosk Lake Medical Centre",
                active=True,
            ),
        ]
    )
    database.add(
        models.DoctorProfile(
            doctor_user_id=doctor_routing.DEMO_DOCTOR_A,
            display_name="Legacy Demo Doctor",
            active=True,
            accepting_patients=True,
        )
    )
    database.flush()
    patient_id = "demo-queue-patient-0001-0"
    legacy_session_id = "demo-queue-0001-0"
    database.add(models.Patient(id=patient_id, name="Legacy Synthetic Patient"))
    database.add(
        models.Session(
            id=legacy_session_id,
            patient_id=patient_id,
            hospital_token="DEMO-Q-0001-1",
            language="en",
            status="ready_for_review",
            hospital_id=doctor_routing.DEMO_HOSPITAL_A,
            selected_doctor_id=doctor_routing.DEMO_DOCTOR_A,
        )
    )
    database.flush()
    database.add(
        models.Consent(
            session_id=legacy_session_id,
            share_with_doctor=True,
            voice_processing=False,
            document_processing=False,
        )
    )
    database.add(
        models.DoctorQueueEntry(
            id="queue-0001-0",
            session_id=legacy_session_id,
            doctor_id=doctor_routing.DEMO_DOCTOR_A,
            hospital_id=doctor_routing.DEMO_HOSPITAL_A,
            status="WAITING",
        )
    )
    database.commit()

    doctor_routing.ensure_demo_routing_data(database)
    doctor_routing.ensure_demo_routing_data(database)

    legacy = database.get(models.Session, legacy_session_id)
    assert legacy.status == "cancelled"
    replacement = database.scalar(
        select(models.Session).where(
            models.Session.patient_id == patient_id,
            models.Session.status == "ready_for_review",
        )
    )
    assert replacement is not None
    UUID(replacement.id)
    assert len(intake.latest_answers(database, replacement.id)) == 5
    assert intake.summary_for(database, replacement.id) is not None


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


def test_patient_queue_estimate_uses_only_selected_doctors_waiting_queue(database):
    hospital = models.Hospital(
        id=str(uuid4()), code=f"TEST-{uuid4()}", name="Queue Test Hospital", active=True
    )
    database.add(hospital)
    database.commit()
    selected_doctor = doctor(database, "Dr. Selected", hospital.id)
    other_doctor = doctor(database, "Dr. Other", hospital.id)
    current_user = patient(database, "current")
    earlier_user = patient(database, "earlier")
    other_user = patient(database, "other-doctor")
    earlier = session_for(database, earlier_user, hospital.id, selected_doctor.id)
    current = session_for(database, current_user, hospital.id, selected_doctor.id)
    other = session_for(database, other_user, hospital.id, other_doctor.id)
    joined_at = datetime.now(timezone.utc)
    database.add_all(
        [
            models.DoctorQueueEntry(
                session_id=earlier.id,
                doctor_id=selected_doctor.id,
                hospital_id=hospital.id,
                status="WAITING",
                joined_at=joined_at - timedelta(minutes=1),
            ),
            models.DoctorQueueEntry(
                session_id=current.id,
                doctor_id=selected_doctor.id,
                hospital_id=hospital.id,
                status="WAITING",
                joined_at=joined_at,
            ),
            models.DoctorQueueEntry(
                session_id=other.id,
                doctor_id=other_doctor.id,
                hospital_id=hospital.id,
                status="WAITING",
                joined_at=joined_at - timedelta(minutes=2),
            ),
        ]
    )
    database.commit()

    estimate = doctor_routing.patient_queue_estimate(database, current.id, current_user)

    assert estimate.doctor_id == selected_doctor.id
    assert estimate.doctor_name == "Dr. Selected"
    assert estimate.position == 2
    assert estimate.estimated_wait_minutes == 10
    assert (
        timedelta(minutes=9, seconds=55)
        <= estimate.expected_meeting_at - datetime.now(timezone.utc)
        <= timedelta(minutes=10)
    )


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
    unassigned = session_for(database, patient(database, "42"), hospital.id)
    unassigned.status = "ready_for_review"
    database.add(
        models.Consent(
            session_id=unassigned.id,
            share_with_doctor=True,
            voice_processing=False,
            document_processing=False,
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
