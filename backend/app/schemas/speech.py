from typing import Literal

from pydantic import ConfigDict, Field

from .common import APIModel, Language


class TranscriptionResult(APIModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["success", "unavailable"]
    transcript: str | None = Field(default=None, max_length=4000)
    candidate_token: str | None = None
    language: Language
    confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    provider: str
    model: str | None = None
    reason: str | None = None


class SpeechSynthesisRequest(APIModel):
    model_config = ConfigDict(extra="forbid")
    question_id: str = Field(min_length=1, max_length=120)


class SpeechSynthesisResult(APIModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["success", "unavailable"]
    audio_base64: str | None = None
    media_type: str = "audio/wav"
    text: str
    language: Language
    provider: str
    reason: str | None = None
