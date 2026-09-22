"""Phase 7 evidence-linked summary contract tests."""

from app.schemas.clinical_summary import EvidenceReference
from app.services.summary_provenance import resolve


def reference(source_type="patient_answer", **metadata):
    return EvidenceReference(
        statement_id="statement-1",
        section="hpi",
        statement_text="Fever for 3 days",
        source_type=source_type,
        source_id="source-1",
        source_text="fever since three days",
        source_metadata=metadata,
    )


def test_patient_reported_summary_provenance():
    item = resolve(reference())
    assert item.badge == "Patient"
    assert "Reported by the patient" in item.provenance_explanation[0]
    assert item.evidence_refs == ["source-1"]


def test_document_provenance_retains_original_page_and_provider():
    item = resolve(
        reference(
            "medical_fact",
            document_id="doc-1",
            document_filename="Prescription.pdf",
            page_number=1,
            bounding_box={"x": 2, "y": 4},
            ocr_provider="mock-ocr",
            ocr_model="v1",
            original_extracted_value="Metformin 500 mg BD",
            verification_status="unverified",
        )
    )
    assert item.badge == "Document — Unverified"
    assert "page 1" in item.provenance_explanation[0]
    assert item.source_metadata["original_extracted_value"] == "Metformin 500 mg BD"
    assert item.source_metadata["bounding_box"] == {"x": 2, "y": 4}
    assert item.source_metadata["ocr_provider"] == "mock-ocr"


def test_document_and_patient_confirmation_provenance():
    item = resolve(
        reference(
            "medical_fact",
            document_filename="Prescription.pdf",
            patient_confirmed=True,
            verification_status="unverified",
            evidence_refs=["document-evidence", "confirmation-evidence"],
        )
    )
    assert item.status == "patient_confirmed"
    assert item.badge == "Patient Confirmed"
    assert "Patient confirmed current use" in item.provenance_explanation[-1]
    assert item.evidence_refs == ["source-1", "document-evidence", "confirmation-evidence"]


def test_clinician_verified_provenance_does_not_remove_original():
    item = resolve(
        reference(
            "medical_fact",
            verification_status="verified",
            original_extracted_value="Fasting glucose 146 mg/dL",
        )
    )
    assert item.status == "clinician_verified"
    assert item.source_metadata["original_extracted_value"] == "Fasting glucose 146 mg/dL"


def test_conflict_provenance_preserves_both_sources():
    item = resolve(
        reference(
            "discrepancy",
            source_a_value="No current medicines",
            source_b_value="Metformin 500 mg",
            evidence_refs=["patient-1", "document-1"],
        )
    )
    assert item.status == "conflicting"
    assert item.evidence_refs == ["source-1", "patient-1", "document-1"]
    assert "Both source values are preserved" in item.provenance_explanation[-1]


def test_red_flag_provenance_references_deterministic_rule():
    item = resolve(reference("alert", rule_id="RF-CARD-001", status="unacknowledged"))
    assert item.badge == "Safety Rule"
    assert "RF-CARD-001" in item.provenance_explanation[0]
    assert "diagnosis" not in " ".join(item.provenance_explanation).lower()


def test_missing_evidence_does_not_fabricate_document_explanation():
    item = resolve(reference(status="not_reported"))
    assert item.status == "not_reported"
    assert all("document" not in line.lower() for line in item.provenance_explanation)


def test_normalized_suggestion_is_not_clinician_verified():
    item = resolve(reference("normalized_fact", provider="mock"))
    assert item.status == "normalized_unverified"
    assert item.badge == "Normalized"


def test_summary_get_is_read_only_and_includes_coverage_packet(client):
    from test_phase8_summary import create_completed_session

    sid = create_completed_session(client)
    url = f"/api/doctor/sessions/{sid}/summary"
    first = client.get(url, headers={"X-Demo-Doctor": "true"})
    second = client.get(url, headers={"X-Demo-Doctor": "true"})
    assert first.status_code == second.status_code == 200
    assert first.json()["generated_structured_json"] == second.json()["generated_structured_json"]
    assert first.json()["evidence"] == second.json()["evidence"]
    packet = first.json()["pre_arrival_packet"]
    assert packet["packet_reference"] == f"mkp:{sid}"
    assert packet["clinical_summary_id"] == first.json()["id"]


def test_doctor_edit_preserves_evidence_refs_and_confirmed_snapshot(client):
    from test_phase8_summary import create_completed_session

    sid = create_completed_session(client)
    url = f"/api/doctor/sessions/{sid}/summary"
    before = client.get(url, headers={"X-Demo-Doctor": "true"}).json()
    edited = client.put(
        url,
        headers={"X-Demo-Doctor": "true"},
        json={"reviewed_text": "Doctor-edited wording", "expected_version": before["version"]},
    ).json()
    assert edited["evidence"] == before["evidence"]
    confirmed = client.post(
        f"{url}/confirm",
        headers={"X-Demo-Doctor": "true"},
        json={"expected_version": edited["version"]},
    ).json()
    assert confirmed["generated_structured_json"] == before["generated_structured_json"]
    assert confirmed["confirmed_text"] == "Doctor-edited wording"


def test_summary_requires_doctor_authorization(client):
    assert (
        client.get("/api/doctor/sessions/00000000-0000-4000-8000-000000000001/summary").status_code
        == 401
    )
