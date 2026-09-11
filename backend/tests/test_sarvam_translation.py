"""Unit tests for Sarvam translation provider and doctor translation endpoints."""

import asyncio
from types import SimpleNamespace

from app.services.sarvam_translation import (
    SarvamTranslationProvider,
    SarvamTranslationSettings,
)
from tests.test_adaptive import selected

STAFF = {"X-Demo-Doctor": "true"}


class _TextClient:
    def __init__(
        self,
        translated_text: str = "My heart is aching.",
        language_code: str = "bn-IN",
        transliterated_text: str = "buker byatha",
        error: Exception | None = None,
    ):
        self.error = error
        self.translate_kwargs = None
        self.identify_kwargs = None
        self.transliterate_kwargs = None

        self._translated_text = translated_text
        self._language_code = language_code
        self._transliterated_text = transliterated_text

    class _TextService:
        def __init__(self, outer):
            self._outer = outer

        async def translate(self, **kwargs):
            self._outer.translate_kwargs = kwargs
            if self._outer.error:
                raise self._outer.error
            return SimpleNamespace(translated_text=self._outer._translated_text)

        async def identify_language(self, **kwargs):
            self._outer.identify_kwargs = kwargs
            if self._outer.error:
                raise self._outer.error
            return SimpleNamespace(language_code=self._outer._language_code)

        async def transliterate(self, **kwargs):
            self._outer.transliterate_kwargs = kwargs
            if self._outer.error:
                raise self._outer.error
            return SimpleNamespace(transliterated_text=self._outer._transliterated_text)

    @property
    def text(self):
        return self._TextService(self)


def _translation_provider(client: _TextClient) -> SarvamTranslationProvider:
    return SarvamTranslationProvider(
        SarvamTranslationSettings(api_key="synthetic-key"),
        client_factory=lambda **_kwargs: client,
    )


def test_translate_bn_to_en_success():
    client = _TextClient(translated_text="Severe chest pain since morning")
    provider = _translation_provider(client)
    res = asyncio.run(
        provider.translate(
            text="সকাল থেকে বুকে তীব্র ব্যথা",
            source_language="bn",
            target_language="en",
        )
    )
    assert res.status == "success"
    assert res.source_text == "সকাল থেকে বুকে তীব্র ব্যথা"
    assert res.translated_text == "Severe chest pain since morning"
    assert res.source_language == "bn"
    assert res.target_language == "en"
    assert res.provider == "sarvam"

    args = client.translate_kwargs
    assert args["input"] == "সকাল থেকে বুকে তীব্র ব্যথা"
    assert args["source_language_code"] == "bn-IN"
    assert args["target_language_code"] == "en-IN"
    assert args["model"] == "mayura:v1"
    assert args["request_options"]["max_retries"] == 0


def test_translate_hi_to_en_success():
    client = _TextClient(translated_text="Pain in the chest")
    provider = _translation_provider(client)
    res = asyncio.run(
        provider.translate(
            text="सीने में दर्द",
            source_language="hi",
            target_language="en",
        )
    )
    assert res.status == "success"
    assert res.translated_text == "Pain in the chest"
    assert client.translate_kwargs["source_language_code"] == "hi-IN"


def test_translate_same_source_and_target_short_circuits():
    client = _TextClient()
    provider = _translation_provider(client)
    res = asyncio.run(
        provider.translate(
            text="Hello world",
            source_language="en",
            target_language="en",
        )
    )
    assert res.status == "success"
    assert res.translated_text == "Hello world"
    assert client.translate_kwargs is None


def test_translate_timeout_maps_to_unavailable():
    client = _TextClient(error=TimeoutError())
    provider = _translation_provider(client)
    res = asyncio.run(
        provider.translate(
            text="বুকে ব্যথা",
            source_language="bn",
            target_language="en",
        )
    )
    assert res.status == "unavailable"
    assert res.reason == "timeout"
    assert res.translated_text is None
    # Source text must still be strictly preserved
    assert res.source_text == "বুকে ব্যথা"


def test_translate_provider_error_maps_to_unavailable():
    client = _TextClient(error=RuntimeError("Sarvam upstream failure"))
    provider = _translation_provider(client)
    res = asyncio.run(
        provider.translate(
            text="বুকে ব্যথা",
            source_language="bn",
            target_language="en",
        )
    )
    assert res.status == "unavailable"
    assert res.reason == "provider_error"
    assert res.source_text == "বুকে ব্যথা"


def test_identify_language_success():
    client = _TextClient(language_code="bn-IN")
    provider = _translation_provider(client)
    res = asyncio.run(provider.identify_language(text="আমার খুব কষ্ট হচ্ছে"))
    assert res.status == "success"
    assert res.detected_language == "bn-IN"
    assert client.identify_kwargs["input"] == "আমার খুব কষ্ট হচ্ছে"


def test_identify_language_provider_error():
    client = _TextClient(error=RuntimeError("NLP model error"))
    provider = _translation_provider(client)
    res = asyncio.run(provider.identify_language(text="Hello"))
    assert res.status == "unavailable"
    assert res.detected_language is None


def test_transliterate_success():
    client = _TextClient(transliterated_text="aamar buke byatha")
    provider = _translation_provider(client)
    res = asyncio.run(
        provider.transliterate(
            text="আমার বুকে ব্যথা",
            source_language="bn",
            target_language="en",
        )
    )
    assert res.status == "success"
    assert res.transliterated_text == "aamar buke byatha"
    assert res.source_text == "আমার বুকে ব্যথা"
    assert client.transliterate_kwargs["source_language_code"] == "bn-IN"


def test_transliterate_provider_error():
    client = _TextClient(error=RuntimeError("Transliteration fault"))
    provider = _translation_provider(client)
    res = asyncio.run(
        provider.transliterate(
            text="বুকে ব্যথা",
            source_language="bn",
            target_language="en",
        )
    )
    assert res.status == "unavailable"
    assert res.reason == "provider_error"
    assert res.source_text == "বুকে ব্যথা"


# --- Doctor Workspace API endpoint integration tests ---


def test_doctor_translate_requires_staff_auth(client):
    sid, _ = selected(client)
    url = f"/api/doctor/sessions/{sid}/translate"
    res = client.post(
        url,
        json={"text": "আমার বুকে ব্যথা", "source_language": "bn", "target_language": "en"},
    )
    assert res.status_code == 401


def test_doctor_translate_endpoint_with_mock_provider(client):
    sid, _ = selected(client)
    url = f"/api/doctor/sessions/{sid}/translate"
    res = client.post(
        url,
        headers=STAFF,
        json={"text": "আমার বুকে ব্যথা", "source_language": "bn", "target_language": "en"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["source_text"] == "আমার বুকে ব্যথা"
    assert data["source_language"] == "bn"
    assert data["target_language"] == "en"
    assert len(data["translated_text"]) > 0


def test_doctor_transliterate_endpoint_with_mock_provider(client):
    sid, _ = selected(client)
    url = f"/api/doctor/sessions/{sid}/transliterate"
    res = client.post(
        url,
        headers=STAFF,
        json={"text": "আমার বুকে ব্যথা", "source_language": "bn", "target_language": "en"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["source_text"] == "আমার বুকে ব্যথা"
    assert len(data["transliterated_text"]) > 0


def test_doctor_identify_language_endpoint(client):
    sid, _ = selected(client)
    url = f"/api/doctor/sessions/{sid}/identify-language"
    res = client.post(
        url,
        headers=STAFF,
        json={"text": "আমার বুকে তীব্র ব্যথা"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["detected_language"].startswith(("bn", "hi", "en"))

