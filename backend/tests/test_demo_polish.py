import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import select

from app import models
from app.api.deps import DEMO_DOCTOR_ID
from app.services import adaptive
from app.services.clinical_summary import ClinicalSummaryService
from app.services.showcase import ShowcaseService

DOCTOR_HEADERS = {"X-Demo-Doctor": "true"}


def test_seed_showcase_patient_service(database, isolated_document_storage):
    result = ShowcaseService.seed_showcase_patient(database)
    assert result is not None
    assert result["hospital_token"] == "T-SHOWCASE-101"
    assert result["language"] == "bn"
    assert "Sunita Sharma" in result["patient_name"]

    # Verify Database contents
    session = (
        database.query(models.Session)
        .filter(models.Session.hospital_token == "T-SHOWCASE-101")
        .first()
    )
    assert session is not None
    assert session.language == "bn"
    assert session.status == "ready_for_review"

    state = adaptive.state(database, session.id)
    assert state.is_complete is True
    assert state.missing_required == []
    assert len(state.active_answers) == 26
    onset = next(answer for answer in state.active_answers if answer.field == "hpi.onset")
    assert onset.value.model_dump() == {"amount": 1, "unit": "days"}
    assert all(answer.source != "voice" for answer in state.active_answers)

    # Verify Patient
    patient = database.get(models.Patient, session.patient_id)
    assert patient is not None
    assert patient.demo_abha_id == "patient@abdm"

    # Verify Alerts (Emergency + Urgent)
    alerts = (
        database.query(models.Alert)
        .filter(models.Alert.session_id == session.id)
        .order_by(models.Alert.priority)
        .all()
    )
    assert len(alerts) >= 2
    rule_ids = {a.rule_id for a in alerts}
    assert "RF-CHEST-001" in rule_ids
    assert "RF-CHEST-002" in rule_ids
    emergency_alert = next(a for a in alerts if a.rule_id == "RF-CHEST-001")
    assert emergency_alert.priority == "emergency"
    emergency_fields = {fact["field"] for fact in emergency_alert.triggering_facts_json}
    assert emergency_fields == {"hpi.severity", "hpi.radiation"}
    urgent_alert = next(a for a in alerts if a.rule_id == "RF-CHEST-002")
    assert urgent_alert.triggering_facts_json[0]["value"] == "DYSPNEA"

    # Verify Documents & Facts
    docs = database.query(models.Document).filter(models.Document.session_id == session.id).all()
    assert len(docs) == 2
    doc_types = {d.document_type for d in docs}
    assert "prescription" in doc_types
    assert "lab_report" in doc_types
    for document in docs:
        fixture_bytes = isolated_document_storage.get_file_bytes(document.object_key)
        assert len(fixture_bytes) == document.file_size_bytes
        assert hashlib.sha256(fixture_bytes).hexdigest() == document.sha256_hash
        assert document.media_type == "image/png"
        assert document.processing_status == "mock_fixture"
        extraction = document.extractions[0]
        assert extraction.extractor == "mock"
        assert extraction.confidence is None
        assert extraction.verification_status == "verified"

    med_facts = (
        database.query(models.MedicationFact)
        .filter(models.MedicationFact.session_id == session.id)
        .all()
    )
    assert len(med_facts) == 3

    lab_facts = database.query(models.LabFact).filter(models.LabFact.session_id == session.id).all()
    assert len(lab_facts) == 4
    assert all(fact.verification_status == "verified" for fact in [*med_facts, *lab_facts])
    assert database.query(models.MedicalFactRevision).count() == len(med_facts) + len(lab_facts)

    # Verify ABDM & HIS records
    abdm = (
        database.query(models.ABDMRecord).filter(models.ABDMRecord.session_id == session.id).first()
    )
    assert abdm is not None
    assert abdm.abha_status == "mock_verified"
    assert abdm.care_context_status == "linked"
    assert abdm.his_dispatch_status == "dispatched"

    # Verify Clinical Summary
    summary = (
        database.query(models.ClinicalSummary)
        .filter(models.ClinicalSummary.session_id == session.id)
        .first()
    )
    assert summary is not None
    assert summary.status in ("generated", "draft")
    assert summary.generated_text is not None
    summary_revision = (
        database.query(models.SummaryRevision)
        .filter(models.SummaryRevision.summary_id == summary.id)
        .one()
    )
    assert summary_revision.revision_type == "initial_draft"
    assert summary_revision.actor_type == "SYSTEM"

    # Verify idempotent re-seed
    reseed_result = ShowcaseService.seed_showcase_patient(database)
    assert reseed_result["session_id"] == session.id
    assert reseed_result["summary_id"] == summary.id
    assert "already exists" in reseed_result["message"]


def test_reset_demo_data_service(database, isolated_document_storage):
    # Seed first
    ShowcaseService.seed_showcase_patient(database)
    assert database.query(models.Session).count() > 0
    object_keys = list(database.scalars(select(models.Document.object_key)))
    file_paths = [isolated_document_storage.get_file_path(key) for key in object_keys]

    # Wipe
    reset_res = ShowcaseService.reset_demo_data(database)
    assert reset_res["success"] is True

    # Check tables are empty
    assert database.query(models.Session).count() == 0
    assert database.query(models.Patient).count() == 0
    assert database.query(models.Alert).count() == 0
    assert database.query(models.Document).count() == 0
    assert database.query(models.MedicationFact).count() == 0
    assert database.query(models.LabFact).count() == 0
    assert database.query(models.ABDMRecord).count() == 0
    assert database.query(models.ClinicalSummary).count() == 0
    assert all(not path.exists() for path in file_paths)
    reset_audit = database.query(models.AuditLog).one()
    assert reset_audit.action == "DEMO_DATA_RESET"

    # Check Demo Doctor User is preserved
    doc_user = database.get(models.User, DEMO_DOCTOR_ID)
    assert doc_user is not None
    assert doc_user.role == "doctor"
    assert doc_user.is_active is True


def test_demo_api_endpoints(client, database):
    # 1. Unauthorized without doctor header
    res = client.post("/api/doctor/demo/seed-showcase")
    assert res.status_code == 401

    res = client.post("/api/doctor/demo/reset")
    assert res.status_code == 401

    # 2. Reset existing data via API
    res = client.post("/api/doctor/demo/reset", headers=DOCTOR_HEADERS)
    assert res.status_code == 200
    assert res.json()["success"] is True

    # 3. Seed showcase via API
    res = client.post("/api/doctor/demo/seed-showcase", headers=DOCTOR_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["hospital_token"] == "T-SHOWCASE-101"
    assert "Sunita Sharma" in data["patient_name"]
    session_id = data["session_id"]

    # 4. Doctor session list contains the showcase session
    res = client.get("/api/doctor/sessions", headers=DOCTOR_HEADERS)
    assert res.status_code == 200
    items = res.json()["items"]
    tokens = [s["hospital_token"] for s in items]
    assert "T-SHOWCASE-101" in tokens

    # 5. Doctor can fetch showcase session detail
    res = client.get(f"/api/doctor/sessions/{session_id}", headers=DOCTOR_HEADERS)
    assert res.status_code == 200
    detail = res.json()
    assert detail["session"]["hospital_token"] == "T-SHOWCASE-101"
    assert detail["session"]["language"] == "bn"
    assert len(detail["alerts"]) >= 2

    documents = database.query(models.Document).filter(models.Document.session_id == session_id).all()
    for document in documents:
        file_res = client.get(
            f"/api/sessions/{session_id}/documents/{document.id}/file",
            headers=DOCTOR_HEADERS,
        )
        assert file_res.status_code == 200
        assert file_res.headers["content-type"] == "image/png"
        assert hashlib.sha256(file_res.content).hexdigest() == document.sha256_hash

    # Check ABDM status
    abdm_res = client.get(f"/api/doctor/sessions/{session_id}/abdm/status", headers=DOCTOR_HEADERS)
    assert abdm_res.status_code == 200
    abdm_data = abdm_res.json()
    assert abdm_data["abha_status"] == "mock_verified"
    assert abdm_data["care_context_status"] == "linked"
    assert abdm_data["his_dispatch_status"] == "dispatched"

    # 6. Reset demo data via API
    res = client.post("/api/doctor/demo/reset", headers=DOCTOR_HEADERS)
    assert res.status_code == 200
    assert res.json()["success"] is True

    # 7. Doctor session list is now empty
    res = client.get("/api/doctor/sessions", headers=DOCTOR_HEADERS)
    assert res.status_code == 200
    assert len(res.json()["items"]) == 0


def test_showcase_api_contract_is_in_openapi(client):
    schema = client.get("/openapi.json").json()
    seed_response = schema["paths"]["/api/doctor/demo/seed-showcase"]["post"]["responses"]["200"]
    reset_response = schema["paths"]["/api/doctor/demo/reset"]["post"]["responses"]["200"]
    assert "ShowcaseSeedResponse" in json.dumps(seed_response)
    assert "DemoResetResponse" in json.dumps(reset_response)


def test_showcase_seed_failure_rolls_back_database_and_files(
    database, isolated_document_storage, monkeypatch
):
    def fail_summary(*_args, **_kwargs):
        raise RuntimeError("synthetic summary failure")

    monkeypatch.setattr(ClinicalSummaryService, "generate_draft", fail_summary)
    with pytest.raises(RuntimeError, match="synthetic summary failure"):
        ShowcaseService.seed_showcase_patient(database)

    assert database.query(models.Session).count() == 0
    assert database.query(models.Patient).count() == 0
    assert database.query(models.Document).count() == 0
    assert not any(path.is_file() for path in isolated_document_storage.base_dir.rglob("*"))


def test_migrated_sqlite_database_can_seed_demo_doctor(tmp_path):
    database_path = tmp_path / "migrated-demo.db"
    environment = {
        **os.environ,
        "APP_ENV": "test",
        "DEMO_MODE": "true",
        "DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
    }
    script = """
from alembic import command
from alembic.config import Config
from app.seed import main

command.upgrade(Config('alembic.ini'), 'head')
main()
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert database_path.is_file()
