"""BHASHINI (ULCA) Real Speech Provider for ASR and TTS.

Complies with MediKiosk Phase 4A/4B invariants:
1. Zero LLM or ASR authority over clinical interview state.
2. Ephemeral audio: raw audio is never written to disk, database, or object storage.
3. Candidate transcription only: transcripts require explicit patient confirmation.
4. Zero secret leakage: all credentials wrapped in Pydantic SecretStr.
5. Graceful failure: provider timeouts or errors return status="unavailable" without crashing intake.
"""

import base64
import json
import logging
import os
import time
from typing import Any
from urllib.parse import urlsplit

import httpx2 as httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.schemas.speech import SpeechSynthesisResult, TranscriptionResult

logger = logging.getLogger(__name__)

DEFAULT_BHASHINI_ENDPOINT = "https://meity-auth.ulca.ai"
DEFAULT_PIPELINE_ID = "64392f96daac500b55c543d6"
DEFAULT_TIMEOUT_SECONDS = 15.0

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

    @classmethod
    def from_environment(cls) -> "BhashiniSettings":
        api_key = os.getenv("BHASHINI_API_KEY", "").strip()
        user_id = os.getenv("BHASHINI_USER_ID", "").strip()
        pipeline_id = os.getenv("BHASHINI_PIPELINE_ID", DEFAULT_PIPELINE_ID).strip()
        endpoint = os.getenv("BHASHINI_ENDPOINT_URL", DEFAULT_BHASHINI_ENDPOINT).rstrip("/")

        parsed = urlsplit(endpoint)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "BHASHINI_ENDPOINT_URL must be an HTTPS base URL without credentials/query/fragment"
            )

        inference_url = os.getenv("BHASHINI_INFERENCE_URL")
        if inference_url:
            inference_url = inference_url.strip()
            inf_parsed = urlsplit(inference_url)
            if (
                inf_parsed.scheme != "https"
                or not inf_parsed.hostname
                or inf_parsed.username
                or inf_parsed.password
            ):
                raise ValueError(
                    "BHASHINI_INFERENCE_URL must be an HTTPS URL without credentials"
                )

        inf_key_raw = os.getenv("BHASHINI_INFERENCE_API_KEY")
        inf_key = SecretStr(inf_key_raw.strip()) if inf_key_raw else None

        try:
            timeout_val = float(os.getenv("BHASHINI_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
        except ValueError:
            raise ValueError("BHASHINI_TIMEOUT_SECONDS must be a positive number") from None

        if not 1.0 <= timeout_val <= 60.0:
            raise ValueError("BHASHINI_TIMEOUT_SECONDS must be between 1.0 and 60.0 seconds")

        return cls(
            api_key=SecretStr(api_key),
            user_id=SecretStr(user_id),
            pipeline_id=pipeline_id,
            endpoint_url=endpoint,
            inference_url=inference_url,
            inference_api_key=inf_key,
            timeout=timeout_val,
        )


class PipelineTaskConfig:
    def __init__(
        self,
        callback_url: str,
        auth_header_name: str,
        auth_header_value: str,
        service_id: str,
        expires_at: float,
    ):
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
    ):
        self.settings = settings or BhashiniSettings.from_environment()
        self._transport = transport
        self._pipeline_cache: dict[str, PipelineTaskConfig] = {}

    def _get_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=self._transport,
            timeout=httpx.Timeout(self.settings.timeout),
        )

    def _map_audio_format(self, media_type: str) -> str:
        normalized = media_type.strip().lower()
        base_mime = normalized.split(";")[0].strip()
        return MIME_TO_AUDIO_FORMAT.get(base_mime, "wav")

    async def _discover_pipeline_task(
        self,
        client: httpx.AsyncClient,
        task_type: str,
        language: str,
    ) -> PipelineTaskConfig:
        cache_key = f"{task_type}:{language}"
        cached = self._pipeline_cache.get(cache_key)
        if cached and not cached.is_expired():
            return cached

        # If direct inference URL is configured with inference key, construct static config
        if self.settings.inference_url:
            auth_val = (
                self.settings.inference_api_key.get_secret_value()
                if self.settings.inference_api_key
                else self.settings.api_key.get_secret_value()
            )
            config = PipelineTaskConfig(
                callback_url=self.settings.inference_url,
                auth_header_name="Authorization",
                auth_header_value=auth_val,
                service_id="",
                expires_at=time.time() + 86400,
            )
            self._pipeline_cache[cache_key] = config
            return config

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
            "Content-Type": "application/json",
        }

        resp = await client.post(discovery_url, json=payload, headers=headers)
        if resp.status_code in (401, 403):
            raise PermissionError("authentication_failed")
        if resp.status_code == 429:
            raise RuntimeError("rate_limited")
        if resp.status_code >= 500:
            raise RuntimeError("provider_error")
        if resp.status_code != 200:
            raise RuntimeError(f"discovery_failed_{resp.status_code}")

        data = resp.json()
        endpoint_info = data.get("pipelineInferenceAPIEndPoint", {})
        callback_url = endpoint_info.get("callbackUrl")
        key_info = endpoint_info.get("inferenceApiKey", {})
        header_name = key_info.get("name", "Authorization")
        header_val = key_info.get("value", "")

        service_id = ""
        tasks = data.get("pipelineResponseConfig", [])
        for task in tasks:
            if task.get("taskType") == task_type:
                configs = task.get("config", [])
                if configs:
                    service_id = configs[0].get("serviceId", "")
                break

        if not callback_url:
            raise ValueError("missing_callback_url")

        # Cache config for 1 hour (3600 seconds)
        config = PipelineTaskConfig(
            callback_url=callback_url,
            auth_header_name=header_name,
            auth_header_value=header_val,
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
        safe_lang = language if language in SUPPORTED_LANGUAGES else "en"
        if language not in SUPPORTED_LANGUAGES:
            return TranscriptionResult(
                status="unavailable",
                transcript=None,
                language=safe_lang,  # type: ignore[arg-type]
                confidence=None,
                provider=self.name,
                model=self.version,
                reason="unsupported_language",
            )

        if not audio:
            return TranscriptionResult(
                status="unavailable",
                transcript=None,
                language=safe_lang,  # type: ignore[arg-type]
                confidence=None,
                provider=self.name,
                model=self.version,
                reason="empty_audio",
            )

        audio_format = self._map_audio_format(media_type)
        audio_b64 = base64.b64encode(audio).decode("ascii")

        try:
            async with self._get_client() as client:
                task_cfg = await self._discover_pipeline_task(client, "asr", language)

                compute_payload = {
                    "pipelineTasks": [
                        {
                            "taskType": "asr",
                            "config": {
                                "language": {
                                    "sourceLanguage": language,
                                },
                                "audioFormat": audio_format,
                                "samplingRate": 16000,
                            },
                        }
                    ],
                    "inputData": {
                        "audio": [
                            {
                                "audioContent": audio_b64,
                            }
                        ]
                    },
                }
                if task_cfg.service_id:
                    compute_payload["pipelineTasks"][0]["config"]["serviceId"] = task_cfg.service_id

                headers = {
                    task_cfg.auth_header_name: task_cfg.auth_header_value,
                    "Content-Type": "application/json",
                }

                resp = await client.post(
                    task_cfg.callback_url,
                    json=compute_payload,
                    headers=headers,
                )

                if resp.status_code in (401, 403):
                    return TranscriptionResult(
                        status="unavailable",
                        transcript=None,
                        language=safe_lang,  # type: ignore[arg-type]
                        confidence=None,
                        provider=self.name,
                        model=self.version,
                        reason="authentication_failed",
                    )
                if resp.status_code == 429:
                    return TranscriptionResult(
                        status="unavailable",
                        transcript=None,
                        language=safe_lang,  # type: ignore[arg-type]
                        confidence=None,
                        provider=self.name,
                        model=self.version,
                        reason="rate_limited",
                    )
                if resp.status_code >= 500:
                    return TranscriptionResult(
                        status="unavailable",
                        transcript=None,
                        language=safe_lang,  # type: ignore[arg-type]
                        confidence=None,
                        provider=self.name,
                        model=self.version,
                        reason="provider_error",
                    )
                if resp.status_code != 200:
                    return TranscriptionResult(
                        status="unavailable",
                        transcript=None,
                        language=safe_lang,  # type: ignore[arg-type]
                        confidence=None,
                        provider=self.name,
                        model=self.version,
                        reason="provider_error",
                    )

                data = resp.json()
                pipeline_resp = data.get("pipelineResponse", [])
                if not pipeline_resp:
                    return TranscriptionResult(
                        status="unavailable",
                        transcript=None,
                        language=safe_lang,  # type: ignore[arg-type]
                        confidence=None,
                        provider=self.name,
                        model=self.version,
                        reason="invalid_response",
                    )

                output = pipeline_resp[0].get("output", [])
                if not output:
                    return TranscriptionResult(
                        status="unavailable",
                        transcript=None,
                        language=safe_lang,  # type: ignore[arg-type]
                        confidence=None,
                        provider=self.name,
                        model=self.version,
                        reason="empty_transcript",
                    )

                transcript = output[0].get("source", "").strip()
                if not transcript:
                    return TranscriptionResult(
                        status="unavailable",
                        transcript=None,
                        language=safe_lang,  # type: ignore[arg-type]
                        confidence=None,
                        provider=self.name,
                        model=self.version,
                        reason="empty_transcript",
                    )

                return TranscriptionResult(
                    status="success",
                    transcript=transcript,
                    language=safe_lang,  # type: ignore[arg-type]
                    confidence=None,  # Strictly null per MediKiosk policy
                    provider=self.name,
                    model=task_cfg.service_id or self.version,
                    reason=None,
                )

        except httpx.TimeoutException:
            logger.warning("Bhashini ASR upstream timeout")
            return TranscriptionResult(
                status="unavailable",
                transcript=None,
                language=safe_lang,  # type: ignore[arg-type]
                confidence=None,
                provider=self.name,
                model=self.version,
                reason="timeout",
            )
        except PermissionError:
            return TranscriptionResult(
                status="unavailable",
                transcript=None,
                language=safe_lang,  # type: ignore[arg-type]
                confidence=None,
                provider=self.name,
                model=self.version,
                reason="authentication_failed",
            )
        except RuntimeError as e:
            reason = str(e)
            if reason not in ("rate_limited", "provider_error"):
                reason = "provider_error"
            return TranscriptionResult(
                status="unavailable",
                transcript=None,
                language=safe_lang,  # type: ignore[arg-type]
                confidence=None,
                provider=self.name,
                model=self.version,
                reason=reason,
            )
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning(f"Bhashini ASR response format error: {type(e).__name__}")
            return TranscriptionResult(
                status="unavailable",
                transcript=None,
                language=safe_lang,  # type: ignore[arg-type]
                confidence=None,
                provider=self.name,
                model=self.version,
                reason="invalid_response",
            )
        except Exception as e:
            logger.warning(f"Bhashini ASR unexpected error: {type(e).__name__}")
            return TranscriptionResult(
                status="unavailable",
                transcript=None,
                language=safe_lang,  # type: ignore[arg-type]
                confidence=None,
                provider=self.name,
                model=self.version,
                reason="provider_error",
            )

    async def synthesize(
        self,
        text: str,
        language: str,
    ) -> SpeechSynthesisResult:
        safe_lang = language if language in SUPPORTED_LANGUAGES else "en"
        if language not in SUPPORTED_LANGUAGES:
            return SpeechSynthesisResult(
                status="unavailable",
                audio_base64=None,
                media_type="audio/wav",
                text=text,
                language=safe_lang,  # type: ignore[arg-type]
                provider=self.name,
                reason="unsupported_language",
            )

        if not text.strip():
            return SpeechSynthesisResult(
                status="unavailable",
                audio_base64=None,
                media_type="audio/wav",
                text=text,
                language=safe_lang,  # type: ignore[arg-type]
                provider=self.name,
                reason="empty_text",
            )

        try:
            async with self._get_client() as client:
                task_cfg = await self._discover_pipeline_task(client, "tts", language)

                compute_payload = {
                    "pipelineTasks": [
                        {
                            "taskType": "tts",
                            "config": {
                                "language": {
                                    "sourceLanguage": language,
                                },
                                "gender": "female",
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
                if task_cfg.service_id:
                    compute_payload["pipelineTasks"][0]["config"]["serviceId"] = task_cfg.service_id

                headers = {
                    task_cfg.auth_header_name: task_cfg.auth_header_value,
                    "Content-Type": "application/json",
                }

                resp = await client.post(
                    task_cfg.callback_url,
                    json=compute_payload,
                    headers=headers,
                )

                if resp.status_code in (401, 403):
                    return SpeechSynthesisResult(
                        status="unavailable",
                        audio_base64=None,
                        media_type="audio/wav",
                        text=text,
                        language=safe_lang,  # type: ignore[arg-type]
                        provider=self.name,
                        reason="authentication_failed",
                    )
                if resp.status_code == 429:
                    return SpeechSynthesisResult(
                        status="unavailable",
                        audio_base64=None,
                        media_type="audio/wav",
                        text=text,
                        language=safe_lang,  # type: ignore[arg-type]
                        provider=self.name,
                        reason="rate_limited",
                    )
                if resp.status_code >= 500:
                    return SpeechSynthesisResult(
                        status="unavailable",
                        audio_base64=None,
                        media_type="audio/wav",
                        text=text,
                        language=safe_lang,  # type: ignore[arg-type]
                        provider=self.name,
                        reason="provider_error",
                    )
                if resp.status_code != 200:
                    return SpeechSynthesisResult(
                        status="unavailable",
                        audio_base64=None,
                        media_type="audio/wav",
                        text=text,
                        language=safe_lang,  # type: ignore[arg-type]
                        provider=self.name,
                        reason="provider_error",
                    )

                data = resp.json()
                pipeline_resp = data.get("pipelineResponse", [])
                if not pipeline_resp:
                    return SpeechSynthesisResult(
                        status="unavailable",
                        audio_base64=None,
                        media_type="audio/wav",
                        text=text,
                        language=safe_lang,  # type: ignore[arg-type]
                        provider=self.name,
                        reason="invalid_response",
                    )

                audio_list = pipeline_resp[0].get("audio", [])
                if not audio_list:
                    return SpeechSynthesisResult(
                        status="unavailable",
                        audio_base64=None,
                        media_type="audio/wav",
                        text=text,
                        language=safe_lang,  # type: ignore[arg-type]
                        provider=self.name,
                        reason="empty_audio",
                    )

                audio_content = audio_list[0].get("audioContent", "")
                audio_format = audio_list[0].get("audioFormat", "wav")
                media_type = f"audio/{audio_format}"

                if not audio_content:
                    return SpeechSynthesisResult(
                        status="unavailable",
                        audio_base64=None,
                        media_type=media_type,
                        text=text,
                        language=safe_lang,  # type: ignore[arg-type]
                        provider=self.name,
                        reason="empty_audio",
                    )

                return SpeechSynthesisResult(
                    status="success",
                    audio_base64=audio_content,
                    media_type=media_type,
                    text=text,
                    language=safe_lang,  # type: ignore[arg-type]
                    provider=self.name,
                    reason=None,
                )

        except httpx.TimeoutException:
            logger.warning("Bhashini TTS upstream timeout")
            return SpeechSynthesisResult(
                status="unavailable",
                audio_base64=None,
                media_type="audio/wav",
                text=text,
                language=safe_lang,  # type: ignore[arg-type]
                provider=self.name,
                reason="timeout",
            )
        except PermissionError:
            return SpeechSynthesisResult(
                status="unavailable",
                audio_base64=None,
                media_type="audio/wav",
                text=text,
                language=safe_lang,  # type: ignore[arg-type]
                provider=self.name,
                reason="authentication_failed",
            )
        except RuntimeError as e:
            reason = str(e)
            if reason not in ("rate_limited", "provider_error"):
                reason = "provider_error"
            return SpeechSynthesisResult(
                status="unavailable",
                audio_base64=None,
                media_type="audio/wav",
                text=text,
                language=safe_lang,  # type: ignore[arg-type]
                provider=self.name,
                reason=reason,
            )
        except Exception as e:
            logger.warning(f"Bhashini TTS unexpected error: {type(e).__name__}")
            return SpeechSynthesisResult(
                status="unavailable",
                audio_base64=None,
                media_type="audio/wav",
                text=text,
                language=safe_lang,  # type: ignore[arg-type]
                provider=self.name,
                reason="provider_error",
            )
