from tests.test_documents import STAFF
from tests.test_phase7_complete import setup_session, upload


def test_medication_evidence_retrieval_returns_real_provenance(client, database):
    session_id = setup_session(client, database)
    document = upload(client, session_id, "metformin_prescription")

    response = client.post(
        f"/api/doctor/sessions/{session_id}/evidence-search",
        headers=STAFF,
        json={"query": "Show medication evidence"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["retrieval_mode"] == "deterministic_patient_scoped"
    assert payload["fallback_used"] is True
    metformin = next(item for item in payload["results"] if item["label"] == "Metformin")
    assert metformin["details"]["dose"] == "500 mg"
    assert metformin["details"]["frequency"] == "Twice Daily"
    assert metformin["source_document_id"] == document["id"]
    assert metformin["source_filename"] == "metformin_prescription.png"
    assert "diagnosis" in payload["disclaimer"].lower()


def test_evidence_retrieval_is_session_scoped_and_staff_only(client, database):
    owner_session = setup_session(client, database)
    other_session = setup_session(client, database)
    upload(client, owner_session, "metformin_prescription")
    upload(client, other_session, "lab_report")

    unauthenticated = client.post(
        f"/api/doctor/sessions/{owner_session}/evidence-search",
        json={"query": "Metformin"},
    )
    assert unauthenticated.status_code != 200

    response = client.post(
        f"/api/doctor/sessions/{other_session}/evidence-search",
        headers=STAFF,
        json={"query": "Metformin"},
    )
    assert response.status_code == 200
    assert all(item["label"] != "Metformin" for item in response.json()["results"])
