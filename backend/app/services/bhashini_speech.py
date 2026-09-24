"""BHASHINI speech provider for optional ASR and question-only TTS.

The adapter retains the two supported configuration modes:

1. Legacy ULCA pipeline discovery using `BHASHINI_API_KEY` and
   `BHASHINI_USER_ID`;
2. Direct Dhruva inference using the canonical inference key and explicit
   ASR/TTS service IDs.

All compute requests are routed through the shared `BhashiniComputeClient`.
"""

import io
import logging
import os
import time
import wave
from typing import Any
from urllib.parse import urlsplit

import httpx2 as httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.schemas.speech import SpeechSynthesisResult, TranscriptionResult
from app.services.bhashini import (
    DEFAULT_BHASHINI_INFERENCE_URL,
    DEFAULT_BHASHINI_TIMEOUT_SECONDS,
    BhashiniComputeClient,
    BhashiniComputeSettings,
    BhashiniError,
    encode_base64,
    parse_asr_response,
    parse_tts_response,
    validate_https_url,
)

logger = logging.getLogger(__name__)

DEFAULT_BHASHINI_ENDPOINT = "https://meity-auth.ulca.ai"
DEFAULT_PIPELINE_ID = "64392f96daac500b55c543d6"
DEFAULT_TIMEOUT_SECONDS = DEFAULT_BHASHINI_TIMEOUT_SECONDS

SUPPORTED_LANGUAGES = {"en", "bn", "hi"}

MIME_TO_AUDIO_FORMAT = {
    "audio/webm": "webm",
    "audio/webm;codecs=opus": "webm",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/ogg": "ogg",
    "audio/mp4": "mp4",
    "audio/m4a": "m4a",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/flac": "flac",
    "audio/aac": "aac",
}


class BhashiniSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    api_key: SecretStr = Field(exclude=True, repr=False)
    user_id: SecretStr = Field(exclude=True, repr=False)
    pipeline_id: str = DEFAULT_PIPELINE_ID
    endpoint_url: str = DEFAULT_BHASHINI_ENDPOINT
    inference_url: str | None = None
    inference_api_key: SecretStr | None = Field(default=None, exclude=True, repr=False)
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    asr_service_id: str | None = None
    tts_service_id: str | None = None

    @classmethod
    def from_environment(cls) -> "BhashiniSettings":
        compute = BhashiniComputeSettings.from_environment()
        api_key = os.getenv("BHASHINI_API_KEY", "").strip()
        user_id = os.getenv("BHASHINI_USER_ID", "").strip()
        pipeline_id = os.getenv("BHASHINI_PIPELINE_ID", DEFAULT_PIPELINE_ID).strip()
        endpoint = os.getenv("BHASHINI_ENDPOINT_URL", DEFAULT_BHASHINI_ENDPOINT).rstrip("/")
        validate_https_url(endpoint, label="BHASHINI_ENDPOINT_URL")

        return cls(
            api_key=SecretStr(api_key),
            user_id=SecretStr(user_id),
            pipeline_id=pipeline_id,
            endpoint_url=endpoint,
            inference_url=(compute.inference_url if compute.inference_url_explicit else None),
            inference_api_key=compute.inference_api_key,
            timeout=compute.timeout,
            asr_service_id=compute.asr_service_id,
            tts_service_id=compute.tts_service_id,
        )


class PipelineTaskConfig:
    def __init__(
        self,
        callback_url: str,
        auth_header_name: str,
        auth_header_value: str,
        service_id: str,
        expires_at: float,
    ) -> None:
        self.callback_url = callback_url
        self.auth_header_name = auth_header_name
        self.auth_header_value = auth_header_value
        self.service_id = service_id
        self.expires_at = expires_at

    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class BhashiniSpeechProvider:
    name: str = "bhashini"
    version: str = "ulca-v0"

    def __init__(
        self,
        settings: BhashiniSettings | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings or BhashiniSettings.from_environment()
        compute_settings = BhashiniComputeSettings(
            inference_url=self.settings.inference_url or DEFAULT_BHASHINI_INFERENCE_URL,
            inference_url_explicit=self.settings.inference_url is not None,
            inference_api_key=self.settings.inference_api_key,
            timeout=self.settings.timeout,
            asr_service_id=self.settings.asr_service_id,
            tts_service_id=self.settings.tts_service_id,
        )
        self._compute_client = BhashiniComputeClient(compute_settings, transport=transport)
        self._pipeline_cache: dict[str, PipelineTaskConfig] = {}

    def _map_audio_format(self, media_type: str) -> str:
        normalized = media_type.strip().lower()
        base_mime = normalized.split(";")[0].strip()
        return MIME_TO_AUDIO_FORMAT.get(base_mime, "wav")

    async def _discover_pipeline_task(
        self,
        task_type: str,
        language: str,
    ) -> PipelineTaskConfig:
        cache_key = f"{task_type}:{language}"
        cached = self._pipeline_cache.get(cache_key)
        if cached and not cached.is_expired():
            return cached

        inference_key = self.settings.inference_api_key
        direct_mode = bool(inference_key or self.settings.inference_url)
        if direct_mode:
            if inference_key is None or not inference_key.get_secret_value():
                raise BhashiniError(task_type, "missing_credential")
            service_id = (
                self.settings.asr_service_id
                if task_type == "asr"
                else self.settings.tts_service_id
            )
            if not service_id:
                raise BhashiniError(task_type, "missing_service_id")
            config = PipelineTaskConfig(
                callback_url=self.settings.inference_url or DEFAULT_BHASHINI_INFERENCE_URL,
                auth_header_name="Authorization",
                auth_header_value=inference_key.get_secret_value(),
                service_id=service_id,
                expires_at=time.time() + 86400,
            )
            self._pipeline_cache[cache_key] = config
            return config

        if (
            not self.settings.api_key.get_secret_value()
            or not self.settings.user_id.get_secret_value()
        ):
            raise BhashiniError(task_type, "authentication_failed")

        discovery_url = f"{self.settings.endpoint_url}/ulca/apis/v0/model/getModelsPipeline"
        payload = {
            "pipelineTasks": [
                {
                    "taskType": task_type,
                    "config": {
                        "language": {
                            "sourceLanguage": language,
                        }
                    },
                }
            ],
            "pipelineRequestConfig": {
                "pipelineId": self.settings.pipeline_id,
            },
        }
        headers = {
            "ulcaApiKey": self.settings.api_key.get_secret_value(),
            "userID": self.settings.user_id.get_secret_value(),
        }
        data = await self._compute_client.post_json(
            endpoint=discovery_url,
            payload=payload,
            task_type=task_type,
            headers=headers,
        )

        endpoint_info = data.get("pipelineInferenceAPIEndPoint")
        if not isinstance(endpoint_info, dict):
            raise BhashiniError(task_type, "invalid_response")
        callback_url = endpoint_info.get("callbackUrl")
        key_info = endpoint_info.get("inferenceApiKey")
        if not isinstance(callback_url, str) or not isinstance(key_info, dict):
            raise BhashiniError(task_type, "invalid_response")
        header_name = key_info.get("name", "Authorization")
        header_value = key_info.get("value", "")
        if not isinstance(header_name, str) or not isinstance(header_value, str):
            raise BhashiniError(task_type, "invalid_response")

        service_id = ""
        tasks = data.get("pipelineResponseConfig")
        if isinstance(tasks, list):
            for task in tasks:
                if isinstance(task, dict) and task.get("taskType") == task_type:
                    configs = task.get("config")
                    if isinstance(configs, list) and configs and isinstance(configs[0], dict):
                        candidate = configs[0].get("serviceId")
                        if isinstance(candidate, str):
                            service_id = candidate
                    break

        if not callback_url or not header_value:
            raise BhashiniError(task_type, "invalid_response")
        parsed_callback = urlsplit(callback_url)
        if (
            parsed_callback.scheme != "https"
            or parsed_callback.hostname != "dhruva-api.bhashini.gov.in"
            or parsed_callback.username
            or parsed_callback.password
            or parsed_callback.query
            or parsed_callback.fragment
            or parsed_callback.port not in (None, 443)
            or header_name.lower() != "authorization"
        ):
            raise BhashiniError(task_type, "invalid_response")
        if not service_id:
            raise BhashiniError(task_type, "missing_service_id")

        config = PipelineTaskConfig(
            callback_url=callback_url,
            auth_header_name=header_name,
            auth_header_value=header_value,
            service_id=service_id,
            expires_at=time.time() + 3600,
        )
        self._pipeline_cache[cache_key] = config
        return config

    async def transcribe(
        self,
        audio: bytes,
        language: str,
        media_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> TranscriptionResult:
        del metadata
        safe_lang = language if language in SUPPORTED_LANGUAGES else "en"
        if language not in SUPPORTED_LANGUAGES:
            return self._unavailable_transcription(safe_lang, "unsupported_language")
        if not audio:
            return self._unavailable_transcription(safe_lang, "empty_audio")

        # The browser pipeline produces 16-kHz mono PCM16 WAV. Keep this strict:
        # native WebM/Opus must never be relabeled as verified WAV.
        try:
            if media_type.split(";", 1)[0].strip().lower() not in ("audio/wav", "audio/x-wav"):
                raise ValueError("unsupported media type")
            with wave.open(io.BytesIO(audio), "rb") as source:
                rate = source.getframerate()
                frame_count = source.getnframes()
                if (
                    source.getnchannels() != 1
                    or source.getsampwidth() != 2
                    or rate != 16000
                    or frame_count == 0
                    or len(source.readframes(frame_count)) != frame_count * 2
                ):
                    raise ValueError("unsupported WAV encoding")
        except (ValueError, wave.Error, EOFError):
            return self._unavailable_transcription(safe_lang, "unsupported_audio_format")

        try:
            task_cfg = await self._discover_pipeline_task("asr", safe_lang)
            payload = {
                "pipelineTasks": [
                    {
                        "taskType": "asr",
                        "config": {
                            "language": {
                                "sourceLanguage": safe_lang,
                            },
                            "audioFormat": "wav",
                            "samplingRate": rate,
                            "serviceId": task_cfg.service_id,
                        },
                    }
                ],
                "inputData": {
                    "audio": [
                        {
                            "audioContent": encode_base64(audio),
                        }
                    ]
                },
            }
            data = await self._compute_client.post_pipeline(
                payload,
                "asr",
                endpoint=task_cfg.callback_url,
                authorization=task_cfg.auth_header_value,
            )
            transcript = parse_asr_response(data)
            if len(transcript) > 4000:
                raise BhashiniError("asr", "invalid_response")
            return TranscriptionResult(
                status="success",
                transcript=transcript,
                language=safe_lang,  # type: ignore[arg-type]
                confidence=None,  # Strictly null for uncalibrated ASR
                provider=self.name,
                model=task_cfg.service_id or self.version,
                reason=None,
            )
        except BhashiniError as error:
            logger.warning("Bhashini ASR unavailable: %s", error.reason)
            return self._unavailable_transcription(safe_lang, error.reason)
        except Exception:
            logger.warning("Bhashini ASR unexpected failure: %s", type(Exception).__name__)
            return self._unavailable_transcription(safe_lang, "provider_error")

    async def synthesize(
        self,
        text: str,
        language: str,
    ) -> SpeechSynthesisResult:
        safe_lang = language if language in SUPPORTED_LANGUAGES else "en"
        if language not in SUPPORTED_LANGUAGES:
            return self._unavailable_synthesis(text, safe_lang, "unsupported_language")
        if not text.strip():
            return self._unavailable_synthesis(text, safe_lang, "empty_text")

        try:
            task_cfg = await self._discover_pipeline_task("tts", safe_lang)
            payload = {
                "pipelineTasks": [
                    {
                        "taskType": "tts",
                        "config": {
                            "language": {
                                "sourceLanguage": safe_lang,
                            },
                            "gender": "female",
                            "serviceId": task_cfg.service_id,
                        },
                    }
                ],
                "inputData": {
                    "input": [
                        {
                            "source": text,
                        }
                    ]
                },
            }
            data = await self._compute_client.post_pipeline(
                payload,
                "tts",
                endpoint=task_cfg.callback_url,
                authorization=task_cfg.auth_header_value,
            )
            audio_content, audio_format = parse_tts_response(data)
            return SpeechSynthesisResult(
                status="success",
                audio_base64=audio_content,
                media_type=f"audio/{audio_format}",
                text=text,
                language=safe_lang,  # type: ignore[arg-type]
                provider=self.name,
                reason=None,
            )
        except BhashiniError as error:
            logger.warning("Bhashini TTS unavailable: %s", error.reason)
            return self._unavailable_synthesis(text, safe_lang, error.reason)
        except Exception:
            logger.warning("Bhashini TTS unexpected failure: %s", type(Exception).__name__)
            return self._unavailable_synthesis(text, safe_lang, "provider_error")

    def _unavailable_transcription(
        self,
        language: str,
        reason: str,
    ) -> TranscriptionResult:
        return TranscriptionResult(
            status="unavailable",
            transcript=None,
            language=language,  # type: ignore[arg-type]
            confidence=None,
            provider=self.name,
            model=self.version,
            reason=reason,
        )

    def _unavailable_synthesis(
        self,
        text: str,
        language: str,
        reason: str,
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
