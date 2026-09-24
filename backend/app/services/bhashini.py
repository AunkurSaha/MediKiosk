"""Shared BHASHINI direct-inference compute client.

The client is deliberately small and task-agnostic: it owns transport, timeout,
JSON encoding/decoding, response-size limits, credential handling, and sanitized
error normalization. Providers build task-specific payloads and map
``BhashiniError.reason`` to their existing result contracts.
"""

import base64
import binascii
import json
import logging
import os
from urllib.parse import urlsplit

import httpx2 as httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr

logger = logging.getLogger(__name__)

DEFAULT_BHASHINI_INFERENCE_URL = (
    "https://dhruva-api.bhashini.gov.in/services/inference/pipeline"
)
DEFAULT_BHASHINI_TIMEOUT_SECONDS = 15.0
BHASHINI_TRANSLATION_MODEL = "ai4bharat/indictrans-v2-all-gpu--t4"
MAX_BHASHINI_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_BHASHINI_AUDIO_BYTES = 8 * 1024 * 1024


def validate_https_url(
    value: str,
    *,
    label: str,
    allow_query: bool = False,
) -> str:
    """Validate an HTTPS URL without credentials, query, or fragment."""
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        and not allow_query
        or parsed.fragment
    ):
        qualifier = "URL" if allow_query else "URL without query/fragment"
        raise ValueError(f"{label} must be an HTTPS {qualifier} without credentials")
    return value


class BhashiniComputeSettings(BaseModel):
    """Non-secret settings and secret credential for direct inference."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    inference_url: str = DEFAULT_BHASHINI_INFERENCE_URL
    inference_url_explicit: bool = False
    inference_api_key: SecretStr | None = Field(default=None, exclude=True, repr=False)
    timeout: float = DEFAULT_BHASHINI_TIMEOUT_SECONDS
    asr_service_id: str | None = None
    tts_service_id: str | None = None

    @classmethod
    def from_environment(cls) -> "BhashiniComputeSettings":
        raw_endpoint = os.getenv("BHASHINI_INFERENCE_URL", "").strip()
        endpoint_explicit = bool(raw_endpoint)
        inference_url = (
            validate_https_url(raw_endpoint, label="BHASHINI_INFERENCE_URL")
            if endpoint_explicit
            else DEFAULT_BHASHINI_INFERENCE_URL
        )

        # Canonical name has precedence over the compatibility alias. An empty
        # value is treated as unset rather than masking the fallback.
        inference_api_key: SecretStr | None = None
        for variable in ("BHASHINI_INFERENCE_API_KEY", "BHASHINI_INFERENCE_KEY"):
            raw_key = os.getenv(variable)
            if raw_key and raw_key.strip():
                inference_api_key = SecretStr(raw_key.strip())
                break

        try:
            timeout = float(
                os.getenv("BHASHINI_TIMEOUT_SECONDS", str(DEFAULT_BHASHINI_TIMEOUT_SECONDS))
            )
        except ValueError:
            raise ValueError("BHASHINI_TIMEOUT_SECONDS must be a positive number") from None
        if not 1.0 <= timeout <= 60.0:
            raise ValueError("BHASHINI_TIMEOUT_SECONDS must be between 1.0 and 60.0 seconds")

        return cls(
            inference_url=inference_url,
            inference_url_explicit=endpoint_explicit,
            inference_api_key=inference_api_key,
            timeout=timeout,
            asr_service_id=(os.getenv("BHASHINI_ASR_SERVICE_ID") or "").strip() or None,
            tts_service_id=(os.getenv("BHASHINI_TTS_SERVICE_ID") or "").strip() or None,
        )


class BhashiniError(Exception):
    """Sanitized provider error; never includes credentials or request payloads."""

    def __init__(
        self,
        task_type: str,
        reason: str,
        *,
        status_code: int | None = None,
    ) -> None:
        self.task_type = task_type
        self.reason = reason
        self.status_code = status_code
        super().__init__(f"Bhashini {task_type} failed: {reason}")


def _failure_reason(status_code: int) -> str:
    if status_code in (401, 403):
        return "authentication_failed"
    if status_code == 429:
        return "rate_limited"
    if status_code == 400:
        return "invalid_request"
    if status_code >= 500:
        return "provider_error"
    return "invalid_request"


class BhashiniComputeClient:
    """One shared JSON client for BHASHINI inference and ULCA discovery requests."""

    def __init__(
        self,
        settings: BhashiniComputeSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self._transport = transport

    @property
    def endpoint(self) -> str:
        return self.settings.inference_url

    async def post_json(
        self,
        *,
        endpoint: str,
        payload: dict[str, object],
        task_type: str,
        headers: dict[str, str],
    ) -> dict[str, object]:
        """POST UTF-8 JSON with a bounded response and normalized errors."""
        try:
            body = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError):
            raise BhashiniError(task_type, "invalid_request") from None

        request_headers = {"Content-Type": "application/json", **headers}
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=httpx.Timeout(self.settings.timeout),
                follow_redirects=False,
                trust_env=False,
            ) as client:
                async with client.stream(
                    "POST",
                    endpoint,
                    content=body,
                    headers=request_headers,
                ) as response:
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > MAX_BHASHINI_RESPONSE_BYTES:
                            raise BhashiniError(task_type, "invalid_response")
                    status_code = response.status_code
        except httpx.TimeoutException:
            logger.warning("Bhashini %s upstream timeout", task_type)
            raise BhashiniError(task_type, "timeout") from None
        except httpx.HTTPError:
            logger.warning("Bhashini %s network failure", task_type)
            raise BhashiniError(task_type, "network_error") from None

        if status_code != 200:
            reason = _failure_reason(status_code)
            logger.warning("Bhashini %s HTTP failure: %s", task_type, reason)
            raise BhashiniError(task_type, reason, status_code=status_code)

        try:
            parsed = json.loads(bytes(content).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.warning("Bhashini %s malformed JSON response", task_type)
            raise BhashiniError(task_type, "invalid_response") from None
        if not isinstance(parsed, dict):
            raise BhashiniError(task_type, "invalid_response")
        return parsed

    async def post_pipeline(
        self,
        payload: dict[str, object],
        task_type: str,
        *,
        endpoint: str | None = None,
        authorization: str | None = None,
    ) -> dict[str, object]:
        """POST a direct inference pipeline request with a raw Authorization value."""
        if authorization is None:
            secret = self.settings.inference_api_key
            if secret is None or not secret.get_secret_value():
                raise BhashiniError(task_type, "missing_credential")
            authorization = secret.get_secret_value()
        if not authorization:
            raise BhashiniError(task_type, "missing_credential")
        return await self.post_json(
            endpoint=endpoint or self.endpoint,
            payload=payload,
            task_type=task_type,
            headers={"Authorization": authorization},
        )


def _pipeline_response(data: dict[str, object], task_type: str) -> dict[str, object]:
    pipeline_response = data.get("pipelineResponse")
    if not isinstance(pipeline_response, list) or not pipeline_response:
        raise BhashiniError(task_type, "invalid_response")
    first = pipeline_response[0]
    if not isinstance(first, dict):
        raise BhashiniError(task_type, "invalid_response")
    return first


def parse_translation_response(data: dict[str, object]) -> str:
    pipeline = _pipeline_response(data, "translation")
    output = pipeline.get("output")
    if not isinstance(output, list) or not output or not isinstance(output[0], dict):
        raise BhashiniError("translation", "empty_response")
    translated = output[0].get("target")
    if not isinstance(translated, str) or not translated.strip():
        raise BhashiniError("translation", "empty_response")
    return translated


def parse_asr_response(data: dict[str, object]) -> str:
    pipeline = _pipeline_response(data, "asr")
    output = pipeline.get("output")
    if not isinstance(output, list) or not output or not isinstance(output[0], dict):
        raise BhashiniError("asr", "empty_response")
    transcript = output[0].get("source")
    if not isinstance(transcript, str) or not transcript.strip():
        raise BhashiniError("asr", "empty_response")
    return transcript


def parse_tts_response(data: dict[str, object]) -> tuple[str, str]:
    pipeline = _pipeline_response(data, "tts")
    audio = pipeline.get("audio")
    if not isinstance(audio, list) or not audio or not isinstance(audio[0], dict):
        raise BhashiniError("tts", "empty_response")
    audio_content = audio[0].get("audioContent")
    audio_format = audio[0].get("audioFormat", "wav")
    if not isinstance(audio_content, str) or not audio_content:
        raise BhashiniError("tts", "empty_response")
    if not isinstance(audio_format, str) or audio_format not in {"wav", "mp3", "ogg"}:
        raise BhashiniError("tts", "invalid_audio")
    try:
        decoded = base64.b64decode(audio_content, validate=True)
    except (ValueError, binascii.Error):
        raise BhashiniError("tts", "invalid_audio") from None
    if not decoded or len(decoded) > MAX_BHASHINI_AUDIO_BYTES:
        raise BhashiniError("tts", "invalid_audio")
    return audio_content, audio_format


def encode_base64(content: bytes) -> str:
    """Base64 helper for request audio; no Unicode transformations are applied."""
    return base64.b64encode(content).decode("ascii")
