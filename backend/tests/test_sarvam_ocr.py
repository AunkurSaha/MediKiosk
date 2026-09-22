"""Unit tests for Sarvam OCR / Document Intelligence provider."""

import asyncio
from types import SimpleNamespace

import pytest

from app.services.sarvam_ocr import (
    SarvamOcrProvider,
    SarvamOcrSettings,
)


@pytest.fixture(autouse=True)
def _fast_sleep(monkeypatch):
    async def _instant_sleep(_seconds):
        return
    monkeypatch.setattr(asyncio, "sleep", _instant_sleep)


class _DocAiMock:
    def __init__(
        self,
        job_id: str = "job-synthetic-123",
        statuses: list[str] | None = None,
        results: dict | None = None,
        digitise_error: Exception | None = None,
        status_error: Exception | None = None,
    ):
        self.job_id = job_id
        self.statuses = statuses or ["pending", "completed"]
        self.status_index = 0
        self.results = results or {
            "documents": [
                {
                    "pages": [
                        {
                            "blocks": [
                                {"text": "Dr. S. Mukherjee, MD"},
                                {"text": "Rx: Tab Metformin 500mg PO BD"},
                                {"text": "Diagnosis: Type 2 Diabetes Mellitus"},
                            ]
                        }
                    ]
                }
            ]
        }
        self.digitise_error = digitise_error
        self.status_error = status_error
        self.digitise_kwargs = None

    def digitise(self, **kwargs):
        self.digitise_kwargs = kwargs
        if self.digitise_error:
            raise self.digitise_error
        return SimpleNamespace(job_id=self.job_id)

    def get_status(self, job_id):
        if self.status_error:
            raise self.status_error
        status = self.statuses[min(self.status_index, len(self.statuses) - 1)]
        self.status_index += 1
        return SimpleNamespace(status=status, job_id=job_id)

    def get_results(self, job_id):
        return self.results


class _Client:
    def __init__(self, doc_ai: _DocAiMock):
        self.doc_ai = doc_ai


def _ocr_provider(doc_ai: _DocAiMock, max_polls: int = 4, poll_interval: float = 0.1) -> SarvamOcrProvider:
    settings = SarvamOcrSettings(
        api_key="synthetic-key",
        timeout=10,
        poll_interval=poll_interval,
        max_polls=max_polls,
    )
    return SarvamOcrProvider(settings, client_factory=lambda **_kwargs: _Client(doc_ai))


def test_ocr_settings_redacts_key(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "synthetic-ocr-key")
    settings = SarvamOcrSettings.from_environment()
    assert settings.api_key.get_secret_value() == "synthetic-ocr-key"
    assert "synthetic-ocr-key" not in repr(settings)
    assert "api_key" not in settings.model_dump()


def test_ocr_rejects_unsupported_media_type():
    doc_ai = _DocAiMock()
    provider = _ocr_provider(doc_ai)
    text, conf, meta = asyncio.run(
        provider.extract(b"not-an-image", "text/plain", "notes.txt")
    )
    assert text == ""
    assert conf is None
    assert meta["reason"] == "unsupported_media_type"
    assert doc_ai.digitise_kwargs is None


def test_ocr_rejects_empty_or_oversized_file():
    doc_ai = _DocAiMock()
    provider = _ocr_provider(doc_ai)

    # Empty
    text, conf, meta = asyncio.run(provider.extract(b"", "image/png", "empty.png"))
    assert text == ""
    assert meta["reason"] == "invalid_file_size"

    # Oversized (>10MB)
    huge = b"0" * (10 * 1024 * 1024 + 1)
    text, conf, meta = asyncio.run(provider.extract(huge, "image/png", "huge.png"))
    assert text == ""
    assert meta["reason"] == "invalid_file_size"


def test_ocr_digitise_and_assemble_success():
    doc_ai = _DocAiMock(statuses=["pending", "completed"])
    provider = _ocr_provider(doc_ai)
    sample_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

    text, conf, meta = asyncio.run(
        provider.extract(sample_png, "image/png", "prescription.png")
    )

    assert "Dr. S. Mukherjee, MD" in text
    assert "Tab Metformin 500mg" in text
    assert conf is None  # Strictly nullable confidence per non-negotiable rule
    assert meta["engine"] == "sarvam"
    assert meta["model"] == "doc-ai-digitise-v1"
    assert meta["job_id"] == "job-synthetic-123"
    assert meta["status"] == "completed"

    args = doc_ai.digitise_kwargs
    assert args["output_format"] == "md"
    assert args["file"][0][0] == "prescription.png"
    assert args["file"][0][2] == "image/png"


def test_ocr_polling_failure():
    doc_ai = _DocAiMock(statuses=["pending", "failed"])
    provider = _ocr_provider(doc_ai)
    sample_pdf = b"%PDF-1.4" + b"\x00" * 64

    text, conf, meta = asyncio.run(
        provider.extract(sample_pdf, "application/pdf", "report.pdf")
    )
    assert text == ""
    assert conf is None
    assert meta["reason"] == "job_failed"


def test_ocr_polling_timeout():
    # Never completes within max_polls
    doc_ai = _DocAiMock(statuses=["pending", "pending", "pending", "pending", "pending"])
    provider = _ocr_provider(doc_ai, max_polls=3)
    sample_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

    text, conf, meta = asyncio.run(
        provider.extract(sample_png, "image/png", "prescription.png")
    )
    assert text == ""
    assert conf is None
    assert meta["reason"] == "timeout"


def test_ocr_provider_exception_handling():
    doc_ai = _DocAiMock(digitise_error=RuntimeError("Sarvam doc_ai service unreachable"))
    provider = _ocr_provider(doc_ai)
    sample_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

    text, conf, meta = asyncio.run(
        provider.extract(sample_png, "image/png", "prescription.png")
    )
    assert text == ""
    assert conf is None
    assert meta["reason"] == "provider_error"


def test_parse_prescription_compound_dosage():
    from app.services.document_parser import parse_prescription

    raw_text = """SYNTHETIC MOCK FIXTURE
Dr. R K Sharma, MBBS, MD
Rx:
1. Tab Paracetamol 500mg - 1 tablet TDS after food x 5 days
2. Cap Amoxicillin 250mg - 1 capsule BD x 7 days
3. Tab Pantoprazole 40mg - 1 tablet OD before food x 14 days
4. Syp Cetirizine 5mg/5ml - 5ml HS as needed"""
    parsed = parse_prescription(raw_text)
    meds = parsed["medications"]
    assert len(meds) == 4
    cetirizine = next((m for m in meds if "cetirizine" in m["name"].lower()), None)
    assert cetirizine is not None
    assert cetirizine["dosage"] == "5mg/5ml"
    assert cetirizine["frequency"] == "HS"


def test_parse_prescription_retains_frequency_from_following_instruction_line():
    from app.services.document_parser import parse_prescription

    parsed = parse_prescription(
        "PRESCRIPTION\nMetformin 500 mg\nTake one tablet twice daily\n"
    )

    assert parsed["medications"] == [
        {
            "name": "Metformin",
            "dosage": "500 mg",
            "frequency": "Twice Daily",
            "duration": None,
            "instructions": "Take one tablet twice daily",
        }
    ]


def test_parse_lab_report_sarvam_html_table():
    from app.services.document_parser import parse_lab_report

    html_text = """METROPOLIS DIAGNOSTICS & LABS
Complete Blood Count & Biochemistry
Date: 2026-08-20

<table>
<thead>
<tr>
<th>Test Name</th>
<th>Result</th>
<th>Unit</th>
<th>Reference Range</th>
</tr>
</thead>
<tbody>
<tr>
<td>Hemoglobin</td>
<td>10.5 g/dL</td>
<td>12.0 - 15.5 (Low)</td>
</tr>
<tr>
<td>Fasting Blood Glucose</td>
<td>142 mg/dL</td>
<td>70 - 100 (High)</td>
</tr>
<tr>
<td>Serum Creatinine</td>
<td>1.1 mg/dL</td>
<td>0.6 - 1.2 (Normal)</td>
</tr>
<tr>
<td>Total Cholesterol</td>
<td>210 mg/dL</td>
<td>&lt; 200 (High)</td>
</tr>
</tbody>
</table>"""
    parsed = parse_lab_report(html_text)
    obs = parsed["observations"]
    assert len(obs) == 4
    hb = next((o for o in obs if o["test_name"] == "Hemoglobin"), None)
    assert hb is not None
    assert hb["value"] == "10.5"
    assert hb["unit"] == "g/dL"
    assert hb["flag"] == "low"
    assert hb["reference_range"] == "12.0 - 15.5"

    chol = next((o for o in obs if o["test_name"] == "Total Cholesterol"), None)
    assert chol is not None
    assert chol["value"] == "210"
    assert chol["unit"] == "mg/dL"
    assert chol["flag"] == "high"
    assert chol["reference_range"] == "< 200"


def test_parse_lab_report_markdown_table():
    from app.services.document_parser import parse_lab_report

    md_text = """| Test Name | Result | Unit | Reference Range |
| --- | --- | --- | --- |
| Hemoglobin | 10.5 | g/dL | 12.0 - 15.5 (Low) |
| Total Cholesterol | 210 mg/dL | < 200 (High) |"""
    parsed = parse_lab_report(md_text)
    obs = parsed["observations"]
    assert len(obs) == 2
    assert obs[0]["test_name"] == "Hemoglobin"
    assert obs[0]["value"] == "10.5"
    assert obs[0]["unit"] == "g/dL"
    assert obs[0]["flag"] == "low"
    assert obs[1]["test_name"] == "Total Cholesterol"
    assert obs[1]["value"] == "210"
    assert obs[1]["unit"] == "mg/dL"
    assert obs[1]["flag"] == "high"


def test_sarvam_ocr_e2e_prescription_and_facts(client, monkeypatch):
    import uuid

    mock_text = """Dr. R K Sharma, MBBS, MD
Rx:
1. Tab Paracetamol 500mg - 1 tablet TDS after food x 5 days
2. Syp Cetirizine 5mg/5ml - 5ml HS as needed"""

    doc_ai = _DocAiMock(results={
        "documents": [{"pages": [{"blocks": [{"text": mock_text}]}]}]
    })
    mock_prov = _ocr_provider(doc_ai)
    monkeypatch.setattr("app.services.document_service.get_ocr_provider", lambda: mock_prov)

    session_id = str(uuid.uuid4())
    client.post("/api/sessions", json={
        "id": session_id,
        "patient": {"name": "Test Patient", "demo_abha_id": None},
        "hospital_token": "RX-1234",
        "language": "en",
    })
    client.put(f"/api/sessions/{session_id}/consent", json={
        "voice_processing": False,
        "document_processing": True,
        "share_with_doctor": True,
    })

    from pathlib import Path
    sample_png = (Path(__file__).resolve().parents[2] / "ai/document_fixtures/prescription.png").read_bytes()
    res = client.post(
        f"/api/sessions/{session_id}/documents",
        files={"file": ("rx.png", sample_png, "image/png")},
        data={"document_type": "prescription"},
    )
    assert res.status_code == 201
    doc_data = res.json()
    assert doc_data["processing_status"] == "completed"
    assert len(doc_data["extractions"]) == 1
    ext = doc_data["extractions"][0]
    assert ext["extractor"] == "sarvam"
    assert len(ext["structured_json"]["medications"]) == 2

    facts_res = client.get(
        f"/api/doctor/sessions/{session_id}/medical-facts",
        headers={"X-Demo-Doctor": "true"},
    )
    assert facts_res.status_code == 200
    med_facts = facts_res.json()["medications"]
    assert len(med_facts) == 2
    assert any(m["current"]["name"] == "Syp Cetirizine" for m in med_facts)


def test_sarvam_ocr_e2e_lab_report_and_facts(client, monkeypatch):
    import uuid
    from pathlib import Path

    mock_html = """<table>
<tr><th>Test Name</th><th>Result</th><th>Unit</th><th>Reference Range</th></tr>
<tr><td>Hemoglobin</td><td>10.5 g/dL</td><td>12.0 - 15.5 (Low)</td></tr>
<tr><td>Total Cholesterol</td><td>210 mg/dL</td><td>&lt; 200 (High)</td></tr>
</table>"""

    doc_ai = _DocAiMock(results={
        "documents": [{"pages": [{"blocks": [{"text": mock_html}]}]}]
    })
    mock_prov = _ocr_provider(doc_ai)
    monkeypatch.setattr("app.services.document_service.get_ocr_provider", lambda: mock_prov)

    session_id = str(uuid.uuid4())
    client.post("/api/sessions", json={
        "id": session_id,
        "patient": {"name": "Test Patient", "demo_abha_id": None},
        "hospital_token": "LAB-1234",
        "language": "en",
    })
    client.put(f"/api/sessions/{session_id}/consent", json={
        "voice_processing": False,
        "document_processing": True,
        "share_with_doctor": True,
    })

    sample_png = (Path(__file__).resolve().parents[2] / "ai/document_fixtures/lab_report.png").read_bytes()
    res = client.post(
        f"/api/sessions/{session_id}/documents",
        files={"file": ("lab.png", sample_png, "image/png")},
        data={"document_type": "lab_report"},
    )
    assert res.status_code == 201
    doc_data = res.json()
    assert doc_data["processing_status"] == "completed"
    assert len(doc_data["extractions"]) == 1
    ext = doc_data["extractions"][0]
    assert ext["extractor"] == "sarvam"
    assert len(ext["structured_json"]["observations"]) == 2

    facts_res = client.get(
        f"/api/doctor/sessions/{session_id}/medical-facts",
        headers={"X-Demo-Doctor": "true"},
    )
    assert facts_res.status_code == 200
    lab_facts = facts_res.json()["labs"]
    assert len(lab_facts) == 2
    hb_fact = next(item for item in lab_facts if item["current"]["test_name"] == "Hemoglobin")
    assert hb_fact["current"]["value"] == "10.5"
    assert hb_fact["current"]["flag"] == "low"

    # Also test cross-references endpoint
    xref_res = client.get(
        f"/api/doctor/sessions/{session_id}/cross-references",
        headers={"X-Demo-Doctor": "true"},
    )
    assert xref_res.status_code == 200
    docs = xref_res.json()["documents"]
    assert len(docs) == 1
    assert len(docs[0]["labs"]) == 2
