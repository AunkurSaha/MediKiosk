"""Sarvam REST translation, language identification, and transliteration provider using the pinned official Python SDK."""

import asyncio
import os
from collections.abc import Callable
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sarvamai import AsyncSarvamAI
from sarvamai.errors import ForbiddenError, TooManyRequestsError, UnauthorizedError

from app.schemas.translation import (
    LanguageIdentificationResponse,
    TranslationResponse,
    TransliterationResponse,
)

LANGUAGE_CODES = {
    "en": "en-IN",
    "bn": "bn-IN",
    "hi": "hi-IN",
    "auto": "auto",
}

DEFAULT_TIMEOUT_SECONDS = 12
DEFAULT_TRANSLATION_MODEL = "mayura:v1"


class SarvamTranslationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    api_key: SecretStr = Field(exclude=True, repr=False)
    timeout: int = Field(default=DEFAULT_TIMEOUT_SECONDS, ge=1, le=14)
    translation_model: str = DEFAULT_TRANSLATION_MODEL

    @classmethod
    def from_environment(cls) -> "SarvamTranslationSettings":
        key = os.getenv("SARVAM_API_KEY", "").strip()
        try:
            timeout = int(os.getenv("SARVAM_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
        except ValueError:
            raise ValueError("SARVAM_TIMEOUT_SECONDS must be an integer") from None
        return cls(
            api_key=SecretStr(key),
            timeout=timeout,
            translation_model=os.getenv("SARVAM_TRANSLATION_MODEL", DEFAULT_TRANSLATION_MODEL).strip(),
        )


def _failure_reason(error: Exception) -> str:
    if isinstance(error, (asyncio.TimeoutError, TimeoutError, httpx.TimeoutException)):
        return "timeout"
    if isinstance(error, (UnauthorizedError, ForbiddenError)):
        return "authentication_failed"
    if isinstance(error, TooManyRequestsError):
        return "rate_limited"
    return "provider_error"


class SarvamTranslationProvider:
    name = "sarvam"

    def __init__(
        self,
        settings: SarvamTranslationSettings,
        client_factory: Callable[..., Any] = AsyncSarvamAI,
    ) -> None:
        self.settings = settings
        self.version = settings.translation_model
        self._client = client_factory(
            api_subscription_key=settings.api_key.get_secret_value(),
            timeout=settings.timeout,
        )

    async def translate(
        self,
        text: str,
        source_language: str = "auto",
        target_language: str = "en",
    ) -> TranslationResponse:
        clean_text = text.strip()
        if not clean_text:
            return TranslationResponse(
                status="unavailable",
                source_text=text,
                source_language=source_language,
                target_language=target_language,
                provider=self.name,
                model=self.settings.translation_model,
                reason="empty_text",
            )

        src_code = LANGUAGE_CODES.get(source_language.lower(), source_language)
        tgt_code = LANGUAGE_CODES.get(target_language.lower(), target_language)

        if tgt_code == "auto":
            return TranslationResponse(
                status="unavailable",
                source_text=text,
                source_language=source_language,
                target_language=target_language,
                provider=self.name,
                model=self.settings.translation_model,
                reason="invalid_target_language",
            )

        if src_code != "auto" and src_code == tgt_code:
            return TranslationResponse(
                status="success",
                source_text=text,
                source_language=source_language,
                target_language=target_language,
                translated_text=text,
                provider=self.name,
                model=self.settings.translation_model,
                reason=None,
            )

        try:
            response = await self._client.text.translate(
                input=clean_text,
                source_language_code=src_code,
                target_language_code=tgt_code,
                model=self.settings.translation_model,
                request_options={
                    "timeout_in_seconds": self.settings.timeout,
                    "max_retries": 0,
                },
            )
            translated = getattr(response, "translated_text", "").strip()
            if not translated:
                return TranslationResponse(
                    status="unavailable",
                    source_text=text,
                    source_language=source_language,
                    target_language=target_language,
                    provider=self.name,
                    model=self.settings.translation_model,
                    reason="empty_response",
                )
            return TranslationResponse(
                status="success",
                source_text=text,
                source_language=source_language,
                target_language=target_language,
                translated_text=translated,
                provider=self.name,
                model=self.settings.translation_model,
                reason=None,
            )
        except Exception as error:
            return TranslationResponse(
                status="unavailable",
                source_text=text,
                source_language=source_language,
                target_language=target_language,
                provider=self.name,
                model=self.settings.translation_model,
                reason=_failure_reason(error),
            )

    async def identify_language(self, text: str) -> LanguageIdentificationResponse:
        clean_text = text.strip()
        if not clean_text:
            return LanguageIdentificationResponse(
                status="unavailable",
                provider=self.name,
                reason="empty_text",
            )
        try:
            response = await self._client.text.identify_language(
                input=clean_text,
                request_options={
                    "timeout_in_seconds": self.settings.timeout,
                    "max_retries": 0,
                },
            )
            lang_code = getattr(response, "language_code", None)
            script_code = getattr(response, "script_code", None)
            return LanguageIdentificationResponse(
                status="success",
                detected_language=lang_code,
                script_code=script_code,
                provider=self.name,
                reason=None,
            )
        except Exception as error:
            return LanguageIdentificationResponse(
                status="unavailable",
                provider=self.name,
                reason=_failure_reason(error),
            )

    async def transliterate(
        self,
        text: str,
        source_language: str,
        target_language: str = "en",
    ) -> TransliterationResponse:
        clean_text = text.strip()
        if not clean_text:
            return TransliterationResponse(
                status="unavailable",
                source_text=text,
                source_language=source_language,
                provider=self.name,
                reason="empty_text",
            )

        src_code = LANGUAGE_CODES.get(source_language.lower(), source_language)
        tgt_code = LANGUAGE_CODES.get(target_language.lower(), target_language)

        try:
            response = await self._client.text.transliterate(
                input=clean_text,
                source_language_code=src_code,
                target_language_code=tgt_code,
                request_options={
                    "timeout_in_seconds": self.settings.timeout,
                    "max_retries": 0,
                },
            )
            transliterated = getattr(response, "transliterated_text", "").strip()
            return TransliterationResponse(
                status="success",
                source_text=text,
                source_language=source_language,
                transliterated_text=transliterated,
                provider=self.name,
                reason=None,
            )
        except Exception as error:
            return TransliterationResponse(
                status="unavailable",
                source_text=text,
                source_language=source_language,
                provider=self.name,
                reason=_failure_reason(error),
            )
