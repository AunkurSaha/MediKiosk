from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TranslationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=5000)
    source_language: str = Field(default="auto")
    target_language: str = Field(default="en")


class TranslationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["success", "unavailable"]
    source_text: str
    source_language: str
    target_language: str
    translated_text: str | None = None
    provider: str
    model: str | None = None
    reason: str | None = None
    provenance_note: str = "Machine translation. Patient original wording remains authoritative."


class LanguageIdentificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=5000)


class LanguageIdentificationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["success", "unavailable"]
    detected_language: str | None = None
    script_code: str | None = None
    provider: str
    reason: str | None = None


class TransliterationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=5000)
    source_language: str
    target_language: str = Field(default="en")


class TransliterationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["success", "unavailable"]
    source_text: str
    source_language: str
    transliterated_text: str | None = None
    provider: str
    reason: str | None = None
    provenance_note: str = "Machine transliteration. Original script remains authoritative."
