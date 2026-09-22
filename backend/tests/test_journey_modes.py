import uuid

from app import models
from app.services import doctor_routing


def _create(client, *, mode="PRE_ARRIVAL", hospital_id=None):
    session_id = str(uuid.uuid4())
    response = client.post(
        "/api/sessions",
        json={
            "id": session_id,
            "patient": {"name": "Synthetic Journey Patient"},
            "hospital_token": f"JOURNEY-{session_id[:8]}",
            "language": "en",
            "journey_mode": mode,
            "hospital_id": hospital_id,
        },
    )
    assert response.status_code == 201
    return session_id, response.json()


def test_journey_mode_persists_and_mode_switch_clears_stale_facility(client, database):
    doctor_routing.ensure_demo_routing_data(database)
    session_id, created = _create(
        client, mode="ON_SITE", hospital_id=doctor_routing.DEMO_HOSPITAL_A
    )
    assert created["journey_mode"] == "ON_SITE"
    assert created["hospital_id"] == doctor_routing.DEMO_HOSPITAL_A

    resumed = client.get(f"/api/sessions/{session_id}")
    assert resumed.status_code == 200
    assert resumed.json()["session"]["journey_mode"] == "ON_SITE"

    changed = client.put(
        f"/api/sessions/{session_id}/journey-mode",
        json={"journey_mode": "PRE_ARRIVAL"},
    )
    assert changed.status_code == 200
    assert changed.json()["journey_mode"] == "PRE_ARRIVAL"
    assert changed.json()["hospital_id"] is None
    assert changed.json()["selected_doctor_id"] is None


def test_on_site_mediroute_is_rejected_without_changing_safety_flow(client, database):
    doctor_routing.ensure_demo_routing_data(database)
    session_id, _ = _create(
        client, mode="ON_SITE", hospital_id=doctor_routing.DEMO_HOSPITAL_A
    )
    database.add(
        models.Consent(
            session_id=session_id,
            share_with_doctor=True,
            voice_processing=False,
            document_processing=False,
        )
    )
    database.commit()
    response = client.get(f"/api/sessions/{session_id}/mediroute")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MEDIROUTE_NOT_APPLICABLE"


def test_default_journey_mode_preserves_pre_arrival_compatibility(client):
    _, created = _create(client)
    assert created["journey_mode"] == "PRE_ARRIVAL"
