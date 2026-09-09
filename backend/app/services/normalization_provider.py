import asyncio
import json
import os
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.schemas.normalization import Concept, ProviderInput, ProviderResult


class UnsupportedLanguage(Exception):
    pass


class ProviderUnavailable(Exception):
    pass


class ProviderFailure(Exception):
    """Only application-owned reason codes cross the vendor boundary."""

    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


class ClinicalNormalizationProvider(Protocol):
    name: str
    version: str

    async def normalize(self, request: ProviderInput) -> object:
        """Return untrusted structured output; use nonblocking I/O and honor cancellation."""
        ...


class ConceptDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    display: str = Field(min_length=1, max_length=100)
    value: bool | str


def match_key(text):
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


@lru_cache
def concept_catalog():
    path = Path(__file__).resolve().parents[3] / "ai" / "ontology" / "normalization_concepts.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    TypeAdapter(dict[Concept, ConceptDefinition]).validate_python(data)
    return data


@lru_cache
def vocabulary():
    path = Path(__file__).resolve().parents[3] / "ai" / "normalization" / "mock_vocabulary.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if (
        set(data) != {"version", "content_status", "fixtures"}
        or data["content_status"] != "prototype_unvalidated"
    ):
        raise ValueError("Invalid normalization vocabulary metadata")
    index = {}
    for item in data["fixtures"]:
        if set(item) != {"text", "language", "status", "facts"}:
            raise ValueError("Invalid normalization fixture keys")
        key = (item["language"], match_key(item["text"]))
        if not key[1] or key in index:
            raise ValueError("Empty or duplicate normalization fixture")
        result = ProviderResult.model_validate(
            {
                "schema_version": "1.0",
                "canonical_field": "fixture",
                "language": item["language"],
                "status": item["status"],
                "facts": [{**fact, "evidence": item["text"]} for fact in item["facts"]],
            }
        )
        if any(f.concept not in concept_catalog() for f in result.facts):
            raise ValueError("Fixture concept missing from display catalog")
        index[key] = result
    return data, index


class MockClinicalNormalizationProvider:
    name = "mock"

    @property
    def version(self):
        return vocabulary()[0]["version"]

    async def normalize(self, request: ProviderInput) -> object:
        if request.language not in ("en", "bn", "hi"):
            raise UnsupportedLanguage()
        found = vocabulary()[1].get((request.language, match_key(request.text)))
        result = (
            found.model_dump()
            if found
            else {"schema_version": "1.0", "status": "unrecognized", "facts": []}
        )
        result.update(canonical_field=request.canonical_field, language=request.language)
        # Matching may fold whitespace/case, but source evidence is always the untouched input.
        for fact in result["facts"]:
            fact["evidence"] = request.text
        return result


class DisabledProvider:
    name = "disabled"
    version = "1.0"

    async def normalize(self, request: ProviderInput) -> object:
        raise ProviderUnavailable()


def configured_provider() -> ClinicalNormalizationProvider:
    name = os.getenv("CLINICAL_NORMALIZATION_PROVIDER", "mock")
    if name == "mock":
        return MockClinicalNormalizationProvider()
    if name == "disabled":
        return DisabledProvider()
    if name == "nvidia":
        from app.services.nvidia_normalization import NvidiaClinicalNormalizationProvider

        return NvidiaClinicalNormalizationProvider()
    raise ValueError(
        "CLINICAL_NORMALIZATION_PROVIDER must be mock or disabled or nvidia"
    )


def timeout_seconds():
    default = "8" if os.getenv("CLINICAL_NORMALIZATION_PROVIDER") == "nvidia" else "0.5"
    try:
        timeout = float(os.getenv("CLINICAL_NORMALIZATION_TIMEOUT_SECONDS", default))
    except ValueError:
        raise ValueError("Invalid CLINICAL_NORMALIZATION_TIMEOUT_SECONDS") from None
    if not 0.01 <= timeout <= 15:
        raise ValueError("CLINICAL_NORMALIZATION_TIMEOUT_SECONDS must be between 0.01 and 15")
    return timeout


def validate_configuration():
    configured_provider()
    timeout_seconds()
    vocabulary()


async def invoke(provider: ClinicalNormalizationProvider, request: ProviderInput, timeout: float):
    return await asyncio.wait_for(provider.normalize(request), timeout=timeout)
