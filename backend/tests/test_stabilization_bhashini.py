import asyncio

from pydantic import SecretStr

from app.services.bhashini_speech import BhashiniSettings, BhashiniSpeechProvider
from app.services.speech_provider import get_speech_provider, validate_speech_configuration


def test_direct_inference_configuration_does_not_require_discovery_credentials(monkeypatch):
    monkeypatch.setenv("SPEECH_PROVIDER", "bhashini")
    monkeypatch.setenv("BHASHINI_API_KEY", "")
    monkeypatch.setenv("BHASHINI_USER_ID", "")
    monkeypatch.setenv("BHASHINI_INFERENCE_URL", "https://dhruva-api.bhashini.gov.in/compute")
    monkeypatch.setenv("BHASHINI_INFERENCE_API_KEY", "synthetic-key")
    validate_speech_configuration()


def test_provider_factory_preserves_discovery_cache(monkeypatch):
    monkeypatch.setenv("SPEECH_PROVIDER", "bhashini")
    assert get_speech_provider() is get_speech_provider()


def test_unverified_native_audio_not_mislabeled_as_16khz():
    provider = BhashiniSpeechProvider(
        BhashiniSettings(api_key=SecretStr(""), user_id=SecretStr(""))
    )
    result = asyncio.run(provider.transcribe(b"native webm bytes", "en", "audio/webm"))
    assert result.status == "unavailable"
    assert result.reason == "unsupported_audio_format"
