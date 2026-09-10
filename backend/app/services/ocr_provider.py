import hashlib
import json
import os
from pathlib import Path
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
    version: str = "explicit-fixture-2.0"

    async def extract(
        self,
        image_bytes: bytes,
        media_type: str,
        filename: str,
    ) -> tuple[str, float | None, dict[str, Any]]:
        catalog_path = Path(__file__).resolve().parents[3] / "ai/document_fixtures/catalog.json"
        fixture = json.loads(catalog_path.read_text(encoding="utf-8")).get(hashlib.sha256(image_bytes).hexdigest())
        if fixture is None:
            return "", None, {"engine": self.name, "reason": "real_ocr_not_implemented"}
        return fixture["raw_text"], None, {"engine": self.name, "fixture_id": fixture["fixture_id"]}



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
