import asyncio
import base64
import io
import json
import wave
from types import SimpleNamespace

import httpx2 as httpx
import pytest
from pydantic import SecretStr

from app.schemas.translation import TranslationResponse
from app.services.bhashini import (
    BHASHINI_TRANSLATION_MODEL,
    DEFAULT_BHASHINI_INFERENCE_URL,
    BhashiniComputeClient,
    BhashiniComputeSettings,
)
from app.services.bhashini_speech import BhashiniSettings, BhashiniSpeechProvider
from app.services.bhashini_translation import BhashiniTranslationProvider
from app.services.speech_provider import get_speech_provider
from app.services.translation_provider import get_translation_provider

HINDI = "मुझे दो दिन से बुखार है।"
BENGALI = "আমার দুই দিন ধরে জ্বর হয়েছে।"


def pcm_wav():
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * 160)
    return output.getvalue()


def settings(key="synthetic-inference-key"):
    return BhashiniComputeSettings(
        inference_api_key=SecretStr(key),
        timeout=15.0,
    )


def translation_response(text):
    return {"pipelineResponse": [{"output": [{"target": text}]}]}


def compute_settings(key="synthetic-inference-key"):
    return BhashiniSettings(
        api_key=SecretStr("legacy-key"),
        user_id=SecretStr("legacy-user"),
        inference_api_key=SecretStr(key),
        asr_service_id="synthetic-asr-service",
        tts_service_id="synthetic-tts-service",
    )


def test_shared_client_uses_default_endpoint_raw_auth_unicode_json():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=translation_response(HINDI))

    client = BhashiniComputeClient(settings(), transport=httpx.MockTransport(handler))
    payload = {"inputData": {"input": [{"source": "I have had a fever for two days."}]}}
    result = asyncio.run(client.post_pipeline(payload, "translation"))

    assert str(requests[0].url) == DEFAULT_BHASHINI_INFERENCE_URL
    assert requests[0].headers["Authorization"] == "synthetic-inference-key"
    assert not requests[0].headers["Authorization"].startswith("Bearer ")
    assert requests[0].headers["Content-Type"] == "application/json"
    assert json.loads(requests[0].content.decode("utf-8")) == payload
    assert result["pipelineResponse"][0]["output"][0]["target"] == HINDI


def test_credential_precedence_and_no_secret_serialization(monkeypatch):
    monkeypatch.setenv("BHASHINI_INFERENCE_API_KEY", "primary-key")
    monkeypatch.setenv("BHASHINI_INFERENCE_KEY", "fallback-key")
    primary = BhashiniComputeSettings.from_environment()
    assert primary.inference_api_key.get_secret_value() == "primary-key"

    monkeypatch.setenv("BHASHINI_INFERENCE_API_KEY", "")
    fallback = BhashiniComputeSettings.from_environment()
    assert fallback.inference_api_key.get_secret_value() == "fallback-key"
    assert "fallback-key" not in repr(fallback)
    assert "inference_api_key" not in fallback.model_dump()


@pytest.mark.parametrize(
    ("source", "target", "text", "translated"),
    [
        ("en", "hi", "I have had a fever for two days.", HINDI),
        ("hi", "en", HINDI, "I have had a fever for two days."),
        ("en", "bn", "I have had a fever for two days.", BENGALI),
        ("bn", "en", BENGALI, "I have had a fever for two days."),
    ],
)
def test_translation_pairs_and_unicode(source, target, text, translated):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=translation_response(translated))

    provider = BhashiniTranslationProvider(settings(), transport=httpx.MockTransport(handler))
    result = asyncio.run(provider.translate(text, source, target))

    assert result.status == "success"
    assert result.source_text == text
    assert result.translated_text == translated
    assert result.provider == "bhashini"
    assert result.model == BHASHINI_TRANSLATION_MODEL
    body = json.loads(requests[0].content.decode("utf-8"))
    assert body == {
        "pipelineTasks": [
            {
                "taskType": "translation",
                "config": {
                    "language": {"sourceLanguage": source, "targetLanguage": target},
                    "serviceId": BHASHINI_TRANSLATION_MODEL,
                },
            }
        ],
        "inputData": {"input": [{"source": text}]},
    }
    assert body["inputData"]["input"][0]["source"] == text
    assert TranslationResponse.model_validate(result.model_dump()).translated_text == translated


def test_translation_errors_are_sanitized_and_source_preserved():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "invalid synthetic key"})

    provider = BhashiniTranslationProvider(settings(), transport=httpx.MockTransport(handler))
    result = asyncio.run(provider.translate(HINDI, "hi", "en"))
    assert result.status == "unavailable"
    assert result.reason == "authentication_failed"
    assert result.source_text == HINDI
    assert "synthetic-inference-key" not in result.model_dump_json()
    assert result.model_dump()["reason"] == "authentication_failed"


def test_translation_malformed_and_missing_response():
    for response in (httpx.Response(200, text="not-json"), httpx.Response(200, json={})):
        provider = BhashiniTranslationProvider(
            settings(), transport=httpx.MockTransport(lambda request: response)
        )
        result = asyncio.run(provider.translate("hello", "en", "hi"))
        assert result.status == "unavailable"
        assert result.reason == "invalid_response"


def test_translation_missing_credential_and_timeout(monkeypatch):
    for name in ("BHASHINI_INFERENCE_API_KEY", "BHASHINI_INFERENCE_KEY"):
        monkeypatch.delenv(name, raising=False)
    provider = BhashiniTranslationProvider(BhashiniComputeSettings.from_environment())
    result = asyncio.run(provider.translate("hello", "en", "hi"))
    assert result.status == "unavailable"
    assert result.reason == "missing_credential"

    def timeout_handler(request: httpx.Request):
        raise httpx.ReadTimeout("synthetic timeout")

    provider = BhashiniTranslationProvider(settings(), transport=httpx.MockTransport(timeout_handler))
    result = asyncio.run(provider.translate("hello", "en", "hi"))
    assert result.reason == "timeout"


def test_translation_rejects_unsupported_pair_without_request():
    provider = BhashiniTranslationProvider(settings())
    result = asyncio.run(provider.translate("hello", "en", "fr"))
    assert result.status == "unavailable"
    assert result.reason == "unsupported_language_pair"


def test_direct_asr_request_and_unicode_response():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200, json={"pipelineResponse": [{"output": [{"source": HINDI}]}]}
        )

    provider = BhashiniSpeechProvider(
        compute_settings(), transport=httpx.MockTransport(handler)
    )
    result = asyncio.run(provider.transcribe(pcm_wav(), "hi", "audio/wav"))

    assert result.status == "success"
    assert result.transcript == HINDI
    assert result.language == "hi"
    assert result.confidence is None
    assert result.model == "synthetic-asr-service"
    body = json.loads(requests[0].content.decode("utf-8"))
    assert body["pipelineTasks"][0]["config"]["serviceId"] == "synthetic-asr-service"
    assert body["pipelineTasks"][0]["config"]["samplingRate"] == 16000
    assert base64.b64decode(body["inputData"]["audio"][0]["audioContent"]) == pcm_wav()
    assert requests[0].headers["Authorization"] == "synthetic-inference-key"
    assert not requests[0].headers["Authorization"].startswith("Bearer ")


def test_direct_tts_request_and_base64_validation():
    audio_b64 = base64.b64encode(pcm_wav()).decode("ascii")
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"pipelineResponse": [{"audio": [{"audioContent": audio_b64, "audioFormat": "wav"}]}]},
        )

    provider = BhashiniSpeechProvider(
        compute_settings(), transport=httpx.MockTransport(handler)
    )
    result = asyncio.run(provider.synthesize(BENGALI, "bn"))

    assert result.status == "success"
    assert result.audio_base64 == audio_b64
    assert base64.b64decode(result.audio_base64, validate=True) == pcm_wav()
    assert result.media_type == "audio/wav"
    assert result.text == BENGALI
    body = json.loads(requests[0].content.decode("utf-8"))
    assert body["pipelineTasks"][0]["config"]["serviceId"] == "synthetic-tts-service"
    assert body["inputData"]["input"][0]["source"] == BENGALI



def test_speech_direct_mode_requires_service_id():
    provider = BhashiniSpeechProvider(
        BhashiniSettings(
            api_key=SecretStr("legacy-key"),
            user_id=SecretStr("legacy-user"),
            inference_api_key=SecretStr("synthetic-inference-key"),
        )
    )
    result = asyncio.run(provider.transcribe(pcm_wav(), "en", "audio/wav"))
    assert result.status == "unavailable"
    assert result.reason == "missing_service_id"

    tts_result = asyncio.run(provider.synthesize("hello", "en"))
    assert tts_result.status == "unavailable"
    assert tts_result.reason == "missing_service_id"


def test_speech_timeout_and_invalid_tts_audio():
    def timeout_handler(request: httpx.Request):
        raise httpx.ReadTimeout("synthetic timeout")

    provider = BhashiniSpeechProvider(
        compute_settings(), transport=httpx.MockTransport(timeout_handler)
    )
    result = asyncio.run(provider.transcribe(pcm_wav(), "en", "audio/wav"))
    assert result.status == "unavailable"
    assert result.reason == "timeout"

    def bad_audio_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"pipelineResponse": [{"audio": [{"audioContent": "not-base64!", "audioFormat": "wav"}]}]},
        )

    provider = BhashiniSpeechProvider(
        compute_settings(), transport=httpx.MockTransport(bad_audio_handler)
    )
    result = asyncio.run(provider.synthesize("hello", "en"))
    assert result.status == "unavailable"
    assert result.reason == "invalid_audio"


def test_factories_support_bhashini_but_default_to_mock(monkeypatch):
    monkeypatch.delenv("SPEECH_PROVIDER", raising=False)
    monkeypatch.delenv("TRANSLATION_PROVIDER", raising=False)
    assert get_speech_provider().name == "mock"
    assert get_translation_provider().name == "mock"

    monkeypatch.setenv("SPEECH_PROVIDER", "bhashini")
    monkeypatch.setenv("BHASHINI_INFERENCE_API_KEY", "synthetic-key")
    monkeypatch.setenv("BHASHINI_ASR_SERVICE_ID", "synthetic-asr-service")
    monkeypatch.setenv("BHASHINI_TTS_SERVICE_ID", "synthetic-tts-service")
    monkeypatch.setenv("TRANSLATION_PROVIDER", "bhashini")
    assert get_speech_provider().name == "bhashini"
    translation = get_translation_provider()
    assert isinstance(translation, BhashiniTranslationProvider)
    assert translation.name == "bhashini"
