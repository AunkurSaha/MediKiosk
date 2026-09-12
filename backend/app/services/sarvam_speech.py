"""Sarvam REST speech provider using the pinned official Python SDK."""

import asyncio
import base64
import io
import logging
import os
import wave
from collections.abc import Callable
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sarvamai import AsyncSarvamAI
from sarvamai.errors import ForbiddenError, TooManyRequestsError, UnauthorizedError

from app.schemas.speech import SpeechSynthesisResult, TranscriptionResult

LANGUAGE_CODES = {"en": "en-IN", "bn": "bn-IN", "hi": "hi-IN"}
DEFAULT_TIMEOUT_SECONDS = 12
DEFAULT_STT_MODEL = "saaras:v3"
DEFAULT_TTS_MODEL = "bulbul:v3"
DEFAULT_TTS_SPEAKER = "shubh"


class SarvamSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    api_key: SecretStr = Field(exclude=True, repr=False)
    timeout: int = Field(default=DEFAULT_TIMEOUT_SECONDS, ge=1, le=14)
    stt_model: str = DEFAULT_STT_MODEL
    tts_model: str = DEFAULT_TTS_MODEL
    tts_speaker: str = DEFAULT_TTS_SPEAKER

    @classmethod
    def from_environment(cls) -> "SarvamSettings":
        key = os.getenv("SARVAM_API_KEY", "").strip()
        try:
            timeout = int(os.getenv("SARVAM_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
        except ValueError:
            raise ValueError("SARVAM_TIMEOUT_SECONDS must be an integer") from None
        return cls(
            api_key=SecretStr(key),
            timeout=timeout,
            stt_model=(
                os.getenv("SARVAM_ASR_MODEL")
                or os.getenv("SARVAM_STT_MODEL")
                or DEFAULT_STT_MODEL
            ).strip(),
            tts_model=os.getenv("SARVAM_TTS_MODEL", DEFAULT_TTS_MODEL).strip(),
            tts_speaker=os.getenv("SARVAM_TTS_SPEAKER", DEFAULT_TTS_SPEAKER).strip(),
        )


def _valid_pcm_wav(audio: bytes) -> bool:
    try:
        with wave.open(io.BytesIO(audio), "rb") as source:
            frames = source.getnframes()
            return (
                source.getnchannels() == 1
                and source.getsampwidth() == 2
                and source.getframerate() == 16000
                and frames > 0
                and len(source.readframes(frames)) == frames * 2
            )
    except (EOFError, ValueError, wave.Error):
        return False


logger = logging.getLogger(__name__)


def _failure_reason(error: Exception) -> str:
    logger.warning("Sarvam speech error (%s): %s", type(error).__name__, error)
    if isinstance(error, (asyncio.TimeoutError, TimeoutError, httpx.TimeoutException)):
        return "timeout"
    if isinstance(error, (UnauthorizedError, ForbiddenError)):
        return "authentication_failed"
    if isinstance(error, TooManyRequestsError):
        return "rate_limited"
    return "provider_error"


class SarvamSpeechProvider:
    name = "sarvam"

    def __init__(
        self,
        settings: SarvamSettings,
        client_factory: Callable[..., Any] = AsyncSarvamAI,
    ) -> None:
        self.settings = settings
        self.version = settings.stt_model
        self._client_factory = client_factory
        self._loop_id: int | None = None
        self._client: Any = None

    def _get_client(self) -> Any:
        try:
            current_loop = asyncio.get_running_loop()
            current_loop_id = id(current_loop)
        except RuntimeError:
            current_loop_id = None
        if self._client is None or (current_loop_id is not None and self._loop_id != current_loop_id):
            self._client = self._client_factory(
                api_subscription_key=self.settings.api_key.get_secret_value(),
                timeout=self.settings.timeout,
            )
            self._loop_id = current_loop_id
        return self._client

    async def transcribe(
        self,
        audio: bytes,
        language: str,
        media_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> TranscriptionResult:
        del metadata
        safe_language = language if language in LANGUAGE_CODES else "en"
        if media_type.split(";", 1)[0].strip().lower() not in ("audio/wav", "audio/x-wav"):
            return self._unavailable_transcription(safe_language, "unsupported_audio_format")
        if not _valid_pcm_wav(audio):
            return self._unavailable_transcription(safe_language, "unsupported_audio_format")

        try:
            response = await self._get_client().speech_to_text.transcribe(
                file=("recording.wav", audio, "audio/wav"),
                model=self.settings.stt_model,
                mode="transcribe",
                language_code=LANGUAGE_CODES[safe_language],
                input_audio_codec="wav",
                request_options={
                    "timeout_in_seconds": self.settings.timeout,
                    "max_retries": 0,
                },
            )
            transcript = response.transcript.strip()
            if not transcript or len(transcript) > 4000:
                return self._unavailable_transcription(safe_language, "invalid_response")
            return TranscriptionResult(
                status="success",
                transcript=transcript,
                language=safe_language,  # type: ignore[arg-type]
                confidence=None,
                provider=self.name,
                model=self.settings.stt_model,
                reason=None,
            )
        except Exception as error:
            return self._unavailable_transcription(safe_language, _failure_reason(error))

    async def synthesize(self, text: str, language: str) -> SpeechSynthesisResult:
        safe_language = language if language in LANGUAGE_CODES else "en"
        if not text.strip():
            return self._unavailable_synthesis(text, safe_language, "empty_text")
        try:
            response = await self._get_client().text_to_speech.convert(
                text=text,
                language_code=LANGUAGE_CODES[safe_language],
                speaker=self.settings.tts_speaker,
                speech_sample_rate=16000,
                model=self.settings.tts_model,
                output_audio_codec="wav",
                request_options={
                    "timeout_in_seconds": self.settings.timeout,
                    "max_retries": 0,
                },
            )
            audio = response.audios[0] if response.audios else ""
            base64.b64decode(audio, validate=True)
            if not audio:
                raise ValueError("empty audio")
            return SpeechSynthesisResult(
                status="success",
                audio_base64=audio,
                media_type="audio/wav",
                text=text,
                language=safe_language,  # type: ignore[arg-type]
                provider=self.name,
                reason=None,
            )
        except Exception as error:
            return self._unavailable_synthesis(text, safe_language, _failure_reason(error))

    def _unavailable_transcription(self, language: str, reason: str) -> TranscriptionResult:
        return TranscriptionResult(
            status="unavailable",
            transcript=None,
            language=language,  # type: ignore[arg-type]
            confidence=None,
            provider=self.name,
            model=self.settings.stt_model,
            reason=reason,
        )

    def _unavailable_synthesis(
        self, text: str, language: str, reason: str
    ) -> SpeechSynthesisResult:
        return SpeechSynthesisResult(
            status="unavailable",
            audio_base64=None,
            media_type="audio/wav",
            text=text,
            language=language,  # type: ignore[arg-type]
            provider=self.name,
            reason=reason,
        )
