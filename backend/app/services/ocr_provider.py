import os
from typing import Any, Protocol

DEFAULT_MOCK_PRESCRIPTION = """Dr. R. K. Sharma, MBBS, MD
City Health Clinic & Diagnostic Centre
Date: 2026-08-15
Patient Name: Patient

Rx:
1. Tab Paracetamol 500mg - 1 tablet TDS after food x 5 days
2. Cap Amoxicillin 250mg - 1 capsule BD x 7 days
3. Tab Pantoprazole 40mg - 1 tablet OD before food x 14 days
4. Syp Cetirizine 5mg/5ml - 5ml HS as needed
"""

DEFAULT_MOCK_LAB_REPORT = """METROPOLIS DIAGNOSTICS & LABS
Complete Blood Count & Biochemistry
Date: 2026-08-20

Test Name                 Result      Unit         Reference Range
Hemoglobin                10.5        g/dL         12.0 - 15.5      (Low)
Fasting Blood Glucose     142         mg/dL        70 - 100         (High)
Serum Creatinine          1.1         mg/dL        0.6 - 1.2        (Normal)
Total Cholesterol         210         mg/dL        < 200            (High)
"""


class OcrProvider(Protocol):
    name: str
    version: str

    async def extract(
        self,
        image_bytes: bytes,
        media_type: str,
        filename: str,
    ) -> tuple[str, float | None, dict[str, Any]]: ...


class MockOcrProvider:
    name: str = "mock"
    version: str = "mock-1.0"

    async def extract(
        self,
        image_bytes: bytes,
        media_type: str,
        filename: str,
    ) -> tuple[str, float | None, dict[str, Any]]:
        lower_name = filename.lower()
        if any(k in lower_name for k in ("lab", "report", "blood", "test", "cbc")):
            raw_text = DEFAULT_MOCK_LAB_REPORT
            confidence = 0.95
            doc_type = "lab_report"
        else:
            raw_text = DEFAULT_MOCK_PRESCRIPTION
            confidence = 0.92
            doc_type = "prescription"

        metadata = {
            "inferred_type": doc_type,
            "media_type": media_type,
            "engine": self.name,
            "file_size": len(image_bytes),
        }
        return raw_text, confidence, metadata


class DisabledOcrProvider:
    name: str = "disabled"
    version: str = "disabled-1.0"

    async def extract(
        self,
        image_bytes: bytes,
        media_type: str,
        filename: str,
    ) -> tuple[str, float | None, dict[str, Any]]:
        return "", None, {"engine": self.name}


def get_ocr_provider() -> OcrProvider:
    provider_name = os.getenv("OCR_PROVIDER", "mock").strip().lower()
    if provider_name == "mock":
        return MockOcrProvider()
    if provider_name == "disabled":
        return DisabledOcrProvider()
    raise RuntimeError(
        f"Unsupported OCR_PROVIDER: '{provider_name}'. Allowed: 'mock', 'disabled'."
    )
