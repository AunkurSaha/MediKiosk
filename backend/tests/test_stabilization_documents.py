import io

import pytest
from PIL import Image
from sqlalchemy import select

from app import models
from app.core.errors import WorkflowError
from app.services import document_service
from app.services.document_parser import parse_lab_report
from app.services.storage import StorageService
from tests.test_documents import _setup_session


def valid_png():
    data = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(data, format="PNG")
    return data.getvalue()


@pytest.mark.parametrize(
    "name,data", [("report.png", b"not an image"), ("report.pdf", b"%PDF-junk")]
)
def test_content_validation_precedes_persistence(client, database, name, data):
    sid = _setup_session(client)
    mime = "image/png" if name.endswith("png") else "application/pdf"
    result = client.post(f"/api/sessions/{sid}/documents", files={"file": (name, data, mime)})
    assert result.status_code == 422
    assert database.scalar(select(models.Document).where(models.Document.session_id == sid)) is None


def test_invalid_document_type_rejected_without_private_logs(client, database, caplog):
    sid = _setup_session(client)
    result = client.post(
        f"/api/sessions/{sid}/documents",
        files={"file": ("private.png", valid_png(), "image/png")},
        data={"document_type": "SYNTHETIC_PRIVATE_TYPE"},
    )
    assert result.status_code == 422
    assert database.scalar(select(models.Document).where(models.Document.session_id == sid)) is None
    assert "SYNTHETIC_PRIVATE_TYPE" not in caplog.text


@pytest.mark.parametrize("provider", ["mock", "disabled"])
def test_arbitrary_upload_never_becomes_canned_clinical_content(client, monkeypatch, provider):
    monkeypatch.setenv("OCR_PROVIDER", provider)
    sid = _setup_session(client)
    result = client.post(
        f"/api/sessions/{sid}/documents",
        files={"file": ("blood_test_report.png", valid_png(), "image/png")},
    )
    assert result.status_code == 201
    assert result.json()["processing_status"] == "unavailable"
    assert result.json()["extractions"] == []


def test_storage_rejects_sibling_prefix_and_absolute_paths(tmp_path):
    storage = StorageService(tmp_path / "uploads")
    for key in ["../uploads_other/file", str(tmp_path / "uploads_other/file")]:
        with pytest.raises(WorkflowError):
            storage._resolve_path(key)


def test_missing_lab_flag_stays_unknown():
    row = parse_lab_report("Hemoglobin                10.5        g/dL         12.0 - 15.5")[
        "observations"
    ][0]
    assert row["flag"] is None


def test_db_failure_cleans_written_file(client, database, monkeypatch, tmp_path):
    storage = StorageService(tmp_path)
    monkeypatch.setattr(document_service, "default_storage", storage)
    sid = _setup_session(client)

    def fail():
        raise RuntimeError("synthetic persistence failure")

    monkeypatch.setattr(database, "commit", fail)
    result = client.post(
        f"/api/sessions/{sid}/documents", files={"file": ("test.png", valid_png(), "image/png")}
    )
    assert result.status_code == 500
    assert not [p for p in tmp_path.rglob("*") if p.is_file()]
