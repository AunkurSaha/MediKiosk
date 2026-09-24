"""BHASHINI translation provider behind the existing TranslationProvider protocol."""

import logging

from app.schemas.translation import (
    LanguageIdentificationResponse,
    TranslationResponse,
    TransliterationResponse,
)
from app.services.bhashini import (
    BHASHINI_TRANSLATION_MODEL,
    BhashiniComputeClient,
    BhashiniComputeSettings,
    BhashiniError,
    parse_translation_response,
)

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGE_PAIRS = {
    ("en", "hi"),
    ("hi", "en"),
    ("en", "bn"),
    ("bn", "en"),
}


class BhashiniTranslationProvider:
    """Explicitly selected translation-only BHASHINI adapter."""

    name = "bhashini"
    version = BHASHINI_TRANSLATION_MODEL

    def __init__(
        self,
        settings: BhashiniComputeSettings | None = None,
        *,
        transport=None,
    ) -> None:
        self.settings = settings or BhashiniComputeSettings.from_environment()
        self._client = BhashiniComputeClient(self.settings, transport=transport)

    async def translate(
        self,
        text: str,
        source_language: str = "auto",
        target_language: str = "en",
    ) -> TranslationResponse:
        if not text.strip():
            return self._unavailable(
                text,
                source_language,
                target_language,
                "empty_text",
            )

        source = source_language.strip().lower()
        target = target_language.strip().lower()
        if (source, target) not in SUPPORTED_LANGUAGE_PAIRS:
            return self._unavailable(
                text,
                source_language,
                target_language,
                "unsupported_language_pair",
            )

        payload = {
            "pipelineTasks": [
                {
                    "taskType": "translation",
                    "config": {
                        "language": {
                            "sourceLanguage": source,
                            "targetLanguage": target,
                        },
                        "serviceId": BHASHINI_TRANSLATION_MODEL,
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

        try:
            data = await self._client.post_pipeline(payload, "translation")
            translated = parse_translation_response(data)
        except BhashiniError as error:
            logger.warning("Bhashini translation unavailable: %s", error.reason)
            return self._unavailable(
                text,
                source_language,
                target_language,
                error.reason,
            )
        except Exception:
            logger.warning("Bhashini translation unexpected failure")
            return self._unavailable(
                text,
                source_language,
                target_language,
                "provider_error",
            )

        return TranslationResponse(
            status="success",
            source_text=text,
            source_language=source_language,
            target_language=target_language,
            translated_text=translated,
            provider=self.name,
            model=self.version,
            reason=None,
        )

    async def identify_language(self, text: str) -> LanguageIdentificationResponse:
        del text
        return LanguageIdentificationResponse(
            status="unavailable",
            provider=self.name,
            reason="unsupported_task",
        )

    async def transliterate(
        self,
        text: str,
        source_language: str,
        target_language: str = "en",
    ) -> TransliterationResponse:
        del target_language
        return TransliterationResponse(
            status="unavailable",
            source_text=text,
            source_language=source_language,
            provider=self.name,
            reason="unsupported_task",
        )

    def _unavailable(
        self,
        text: str,
        source_language: str,
        target_language: str,
        reason: str,
    ) -> TranslationResponse:
        return TranslationResponse(
            status="unavailable",
            source_text=text,
            source_language=source_language,
            target_language=target_language,
            provider=self.name,
            model=self.version,
            reason=reason,
        )
