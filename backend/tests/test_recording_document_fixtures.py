import asyncio
import hashlib
import io
from pathlib import Path

from app.services.ocr_provider import MockOcrProvider
from tests.test_documents import STAFF, _setup_session

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "ai" / "document_fixtures"
LAB_PATH = FIXTURE_DIR / "recording_lab_report.jpg"
PRESCRIPTION_PATH = FIXTURE_DIR / "recording_prescription.png"


def test_recording_fixture_bytes_have_locked_fingerprints():
    assert hashlib.sha256(LAB_PATH.read_bytes()).hexdigest() == (
        "2c9b320a8d7d0612c54f61e4dd2bdd5b56bede525d4431367fb67f300bb3fa1b"
    )
    assert hashlib.sha256(PRESCRIPTION_PATH.read_bytes()).hexdigest() == (
        "032b8459ba5b7af5281d3311f7bd23cb41fe4d932b504fc8e21186d30f6dd3a1"
    )


def test_recording_lab_fixture_extracts_exact_visible_observations():
    text, confidence, metadata = asyncio.run(
        MockOcrProvider().extract(LAB_PATH.read_bytes(), "image/jpeg", "renamed-anything.jpg")
    )
    structured = metadata["structured_document"]
    assert metadata["provider_name"] == "deterministic_document_fixture"
    assert confidence is None
    assert "MASTER. AYAN BERA" in text
    assert structured["patient_name"] == "Master Ayan Bera"
    assert [(row["test_name"], row["value"]) for row in structured["observations"]] == [
        ("Hemoglobin", "13.9"),
        ("R.B.C Count", "4.8"),
        ("Total Leucocyte Count", "6.9"),
        ("Neutrophils", "51"),
        ("Lymphocytes", "46"),
        ("Eosinophils", "02"),
        ("Monocytes", "01"),
        ("Basophils", "00"),
        ("E.S.R. (Westergren), 1st Hr.", "20"),
    ]


def test_recording_prescription_fixture_extracts_exact_visible_medications():
    _, confidence, metadata = asyncio.run(
        MockOcrProvider().extract(
            PRESCRIPTION_PATH.read_bytes(), "image/png", "renamed-prescription.png"
        )
    )
    structured = metadata["structured_document"]
    assert metadata["provider_name"] == "deterministic_document_fixture"
    assert confidence is None
    assert structured["patient_name"] == "Ankan Bera"
    assert structured["complaint"] == "Loose motion, body dehydration, food poisoning"
    assert [row["name"] for row in structured["medications"]] == [
        "ORS Powder",
        "Racecadotril",
        "Azithromycin",
        "Ondansetron",
        "Paracetamol",
        "Probiotic Capsule",
    ]
    assert structured["medications"][1]["dosage"] == "100 mg"
    assert structured["medications"][1]["frequency"] == "TDS"
    assert structured["medications"][1]["duration"] == "3 days"


def test_modified_recording_file_does_not_match_fixture():
    modified = bytearray(PRESCRIPTION_PATH.read_bytes())
    modified[-20] ^= 1
    text, confidence, metadata = asyncio.run(
        MockOcrProvider().extract(bytes(modified), "image/png", PRESCRIPTION_PATH.name)
    )
    assert text == ""
    assert confidence is None
    assert metadata["reason"] == "real_ocr_not_implemented"
    assert "fixture_id" not in metadata


def test_renamed_recording_prescription_persists_normal_provenance(client):
    session_id = _setup_session(client)
    response = client.post(
        f"/api/sessions/{session_id}/documents",
        files={
            "file": (
                "completely-renamed.png",
                io.BytesIO(PRESCRIPTION_PATH.read_bytes()),
                "image/png",
            )
        },
        data={"document_type": "prescription"},
    )
    assert response.status_code == 201
    document = response.json()
    assert document["processing_status"] == "mock_fixture"
    assert document["sha256_hash"] == hashlib.sha256(PRESCRIPTION_PATH.read_bytes()).hexdigest()
    extraction = document["extractions"][0]
    assert extraction["extractor"] == "deterministic_document_fixture"
    assert extraction["verification_status"] == "unverified"
    assert extraction["structured_json"]["patient_name"] == "Ankan Bera"
    assert len(extraction["structured_json"]["medications"]) == 6

    facts_response = client.get(
        f"/api/doctor/sessions/{session_id}/medical-facts", headers=STAFF
    )
    assert facts_response.status_code == 200
    facts = facts_response.json()
    assert any(row["current"]["name"] == "Azithromycin" for row in facts["medications"])
    azithromycin = next(
        row for row in facts["medications"] if row["current"]["name"] == "Azithromycin"
    )
    assert azithromycin["verification_status"] == "unverified"
    assert azithromycin["source"]["document_id"] == document["id"]
    assert azithromycin["source"]["extraction_id"] == extraction["id"]
