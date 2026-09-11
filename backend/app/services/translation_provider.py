"""Translation provider registry and protocol."""

import os
from typing import Protocol

from app.schemas.translation import (
    LanguageIdentificationResponse,
    TranslationResponse,
    TransliterationResponse,
)


class TranslationProvider(Protocol):
    name: str
    version: str

    async def translate(
        self,
        text: str,
        source_language: str = "auto",
        target_language: str = "en",
    ) -> TranslationResponse: ...

    async def identify_language(self, text: str) -> LanguageIdentificationResponse: ...

    async def transliterate(
        self,
        text: str,
        source_language: str,
        target_language: str = "en",
    ) -> TransliterationResponse: ...


class MockTranslationProvider:
    name = "mock"
    version = "deterministic-fixture-1.0"

    _FIXTURES: dict[str, str] = {
        "বুকে তীব্র ব্যথা এবং চাপ লাগছে": "Severe chest pain and feeling of pressure.",
        "গতকাল রাত থেকে শুরু হয়েছে": "Started since last night.",
        "বাম হাতে ব্যথা ছড়িয়ে পড়ছে": "Pain radiating to left arm.",
        "হাঁটার সময় শ্বাসকষ্ট হচ্ছে": "Experiencing shortness of breath while walking.",
        "আমার বুকে ব্যথা করছে": "My chest is hurting.",
        "मेरे सीने में दर्द है": "I have pain in my chest.",
    }

    _TRANSLITERATIONS: dict[str, str] = {
        "বুকে তীব্র ব্যথা এবং চাপ লাগছে": "buke tibro byatha ebong chap lagchhe",
        "আমার বুকে ব্যথা করছে": "amar buke byatha korchhe",
        "मेरे सीने में दर्द है": "mere seene mein dard hai",
    }

    async def translate(
        self,
        text: str,
        source_language: str = "auto",
        target_language: str = "en",
    ) -> TranslationResponse:
        clean = text.strip()
        if not clean:
            return TranslationResponse(
                status="unavailable",
                source_text=text,
                source_language=source_language,
                target_language=target_language,
                provider=self.name,
                model=self.version,
                reason="empty_text",
            )
        translated = self._FIXTURES.get(clean, f"[Mock Translation to {target_language.upper()}]: {clean}")
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
        clean = text.strip()
        if not clean:
            return LanguageIdentificationResponse(
                status="unavailable",
                provider=self.name,
                reason="empty_text",
            )
        # Simple heuristic for mock
        if any("\u0980" <= ch <= "\u09ff" for ch in clean):
            return LanguageIdentificationResponse(
                status="success",
                detected_language="bn-IN",
                script_code="Beng",
                provider=self.name,
            )
        if any("\u0900" <= ch <= "\u097f" for ch in clean):
            return LanguageIdentificationResponse(
                status="success",
                detected_language="hi-IN",
                script_code="Deva",
                provider=self.name,
            )
        return LanguageIdentificationResponse(
            status="success",
            detected_language="en-IN",
            script_code="Latn",
            provider=self.name,
        )

    async def transliterate(
        self,
        text: str,
        source_language: str,
        target_language: str = "en",
    ) -> TransliterationResponse:
        clean = text.strip()
        trans = self._TRANSLITERATIONS.get(clean, clean)
        return TransliterationResponse(
            status="success",
            source_text=text,
            source_language=source_language,
            transliterated_text=trans,
            provider=self.name,
        )


class DisabledTranslationProvider:
    name = "disabled"
    version = "disabled-1.0"

    async def translate(
        self,
        text: str,
        source_language: str = "auto",
        target_language: str = "en",
    ) -> TranslationResponse:
        return TranslationResponse(
            status="unavailable",
            source_text=text,
            source_language=source_language,
            target_language=target_language,
            provider=self.name,
            reason="disabled",
        )

    async def identify_language(self, text: str) -> LanguageIdentificationResponse:
        return LanguageIdentificationResponse(
            status="unavailable",
            provider=self.name,
            reason="disabled",
        )

    async def transliterate(
        self,
        text: str,
        source_language: str,
        target_language: str = "en",
    ) -> TransliterationResponse:
        return TransliterationResponse(
            status="unavailable",
            source_text=text,
            source_language=source_language,
            provider=self.name,
            reason="disabled",
        )


_sarvam_translation_instance = None


def get_translation_provider() -> TranslationProvider:
    provider_name = os.getenv("TRANSLATION_PROVIDER", "mock").strip().lower()
    if provider_name == "mock":
        return MockTranslationProvider()
    if provider_name == "disabled":
        return DisabledTranslationProvider()
    if provider_name == "sarvam":
        global _sarvam_translation_instance
        from app.services.sarvam_translation import (
            SarvamTranslationProvider,
            SarvamTranslationSettings,
        )

        settings = SarvamTranslationSettings.from_environment()
        if _sarvam_translation_instance is None or _sarvam_translation_instance.settings != settings:
            _sarvam_translation_instance = SarvamTranslationProvider(settings)
        return _sarvam_translation_instance
    raise RuntimeError(
        f"Unsupported TRANSLATION_PROVIDER: '{provider_name}'. Allowed: 'mock', 'sarvam', 'disabled'."
    )
