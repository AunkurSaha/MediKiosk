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
