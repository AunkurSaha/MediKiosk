import base64
import io
import json
import uuid
import wave

import httpx2 as httpx
import pytest
from pydantic import SecretStr

from app.schemas.speech import SpeechSynthesisResult, TranscriptionResult
from app.services.bhashini_speech import (
    DEFAULT_BHASHINI_ENDPOINT,
    DEFAULT_PIPELINE_ID,
    BhashiniSettings,
    BhashiniSpeechProvider,
)
from app.services.speech_provider import get_speech_provider, validate_speech_configuration


def pcm_wav():
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * 160)
    return output.getvalue()



# -----------------------------------------------------------------------------
# Fixtures & Helpers
# -----------------------------------------------------------------------------

def _make_discovery_response(task_type="asr", lang="en", service_id="ai4bharat/conformer-gpu"):
    return {
        "pipelineResponseConfig": [
            {
                "taskType": task_type,
                "config": [
                    {
                        "serviceId": service_id,
                        "language": {"sourceLanguage": lang},
                    }
                ],
            }
        ],
        "pipelineInferenceAPIEndPoint": {
            "callbackUrl": "https://dhruva-api.bhashini.gov.in/services/inference/pipeline",
            "inferenceApiKey": {
                "name": "Authorization",
                "value": "mock-inference-token-123",
            },
        },
    }


def _make_asr_compute_response(transcript="severe chest pain"):
    return {
        "pipelineResponse": [
            {
                "taskType": "asr",
                "output": [
                    {
                        "source": transcript,
                    }
                ],
            }
        ]
    }


def _make_tts_compute_response(audio_b64="UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=", audio_format="wav"):
    return {
        "pipelineResponse": [
            {
                "taskType": "tts",
                "audio": [
                    {
                        "audioContent": audio_b64,
                        "audioFormat": audio_format,
                    }
                ],
            }
        ]
    }


# -----------------------------------------------------------------------------
# 1. Settings & Environment Validation
# -----------------------------------------------------------------------------

def test_bhashini_settings_defaults(monkeypatch):
    monkeypatch.setenv("BHASHINI_API_KEY", "test-api-key")
    monkeypatch.setenv("BHASHINI_USER_ID", "test-user-id")
    monkeypatch.delenv("BHASHINI_ENDPOINT_URL", raising=False)
    monkeypatch.delenv("BHASHINI_PIPELINE_ID", raising=False)
    monkeypatch.delenv("BHASHINI_INFERENCE_URL", raising=False)
    monkeypatch.delenv("BHASHINI_TIMEOUT_SECONDS", raising=False)

    settings = BhashiniSettings.from_environment()
    assert settings.api_key.get_secret_value() == "test-api-key"
    assert settings.user_id.get_secret_value() == "test-user-id"
    assert settings.endpoint_url == DEFAULT_BHASHINI_ENDPOINT
    assert settings.pipeline_id == DEFAULT_PIPELINE_ID
    assert settings.timeout == 15.0
    assert settings.inference_url is None

    # Verify secrets are excluded in representations and serialization
    dumped = settings.model_dump()
    assert "api_key" not in dumped
    assert "user_id" not in dumped
    assert "test-api-key" not in repr(settings)
    assert "test-user-id" not in repr(settings)


def test_bhashini_settings_custom_env(monkeypatch):
    monkeypatch.setenv("BHASHINI_API_KEY", "custom-key")
    monkeypatch.setenv("BHASHINI_USER_ID", "custom-user")
    monkeypatch.setenv("BHASHINI_ENDPOINT_URL", "https://custom.bhashini.gov.in")
    monkeypatch.setenv("BHASHINI_PIPELINE_ID", "custom-pipe-999")
    monkeypatch.setenv("BHASHINI_INFERENCE_URL", "https://custom-inf.bhashini.gov.in/compute")
    monkeypatch.setenv("BHASHINI_INFERENCE_API_KEY", "inf-token-abc")
    monkeypatch.setenv("BHASHINI_TIMEOUT_SECONDS", "25.0")

    settings = BhashiniSettings.from_environment()
    assert settings.endpoint_url == "https://custom.bhashini.gov.in"
    assert settings.pipeline_id == "custom-pipe-999"
    assert settings.inference_url == "https://custom-inf.bhashini.gov.in/compute"
    assert settings.inference_api_key.get_secret_value() == "inf-token-abc"
    assert settings.timeout == 25.0


def test_bhashini_settings_invalid_urls(monkeypatch):
    monkeypatch.setenv("BHASHINI_API_KEY", "key")
    monkeypatch.setenv("BHASHINI_USER_ID", "user")

    # Insecure HTTP
    monkeypatch.setenv("BHASHINI_ENDPOINT_URL", "http://insecure.bhashini.gov.in")
    with pytest.raises(ValueError, match="HTTPS"):
        BhashiniSettings.from_environment()

    # Query string forbidden
    monkeypatch.setenv("BHASHINI_ENDPOINT_URL", "https://bhashini.gov.in?token=123")
    with pytest.raises(ValueError, match="HTTPS base URL without credentials"):
        BhashiniSettings.from_environment()

    # Invalid timeout
    monkeypatch.setenv("BHASHINI_ENDPOINT_URL", "https://bhashini.gov.in")
    monkeypatch.setenv("BHASHINI_TIMEOUT_SECONDS", "0.2")
    with pytest.raises(ValueError, match="between 1.0 and 60.0"):
        BhashiniSettings.from_environment()


# -----------------------------------------------------------------------------
# 2. Provider Factory & Validation
# -----------------------------------------------------------------------------

def test_bhashini_provider_factory(monkeypatch):
    monkeypatch.setenv("SPEECH_PROVIDER", "bhashini")
    monkeypatch.setenv("BHASHINI_API_KEY", "key")
    monkeypatch.setenv("BHASHINI_USER_ID", "user")

    provider = get_speech_provider()
    assert isinstance(provider, BhashiniSpeechProvider)
    assert provider.name == "bhashini"
    assert provider.version == "ulca-v0"


def test_bhashini_validation_fails_when_keys_missing(monkeypatch):
    monkeypatch.setenv("SPEECH_PROVIDER", "bhashini")
    monkeypatch.delenv("BHASHINI_API_KEY", raising=False)
    monkeypatch.delenv("BHASHINI_USER_ID", raising=False)

    with pytest.raises(RuntimeError, match="BHASHINI_API_KEY and BHASHINI_USER_ID are required"):
        validate_speech_configuration()


# -----------------------------------------------------------------------------
# 3. Audio Format Mapping
# -----------------------------------------------------------------------------

def test_bhashini_audio_format_mapping():
    provider = BhashiniSpeechProvider(
        settings=BhashiniSettings(
            api_key=SecretStr("k"),
            user_id=SecretStr("u"),
        )
    )
    assert provider._map_audio_format("audio/webm") == "webm"
    assert provider._map_audio_format("audio/webm") == "webm"
    assert provider._map_audio_format("audio/wav") == "wav"
    assert provider._map_audio_format("audio/x-wav") == "wav"
    assert provider._map_audio_format("audio/ogg") == "ogg"
    assert provider._map_audio_format("audio/mp4") == "mp4"
    assert provider._map_audio_format("audio/unknown-type") == "wav"


# -----------------------------------------------------------------------------
# 4. ASR Transcription (Success, Multilingual, Caching)
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_bhashini_transcribe_en_success():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        url_str = str(request.url)
        if "/getModelsPipeline" in url_str:
            body = json.loads(request.content.decode("utf-8"))
            assert body["pipelineTasks"][0]["taskType"] == "asr"
            assert body["pipelineTasks"][0]["config"]["language"]["sourceLanguage"] == "en"
            assert request.headers["ulcaApiKey"] == "key-123"
            assert request.headers["userID"] == "user-456"
            return httpx.Response(200, json=_make_discovery_response("asr", "en", "ai4bharat/conformer-en"))
        elif "/services/inference/pipeline" in url_str:
            assert request.headers["Authorization"] == "mock-inference-token-123"
            body = json.loads(request.content.decode("utf-8"))
            assert body["pipelineTasks"][0]["taskType"] == "asr"
            assert body["pipelineTasks"][0]["config"]["language"]["sourceLanguage"] == "en"
            assert body["pipelineTasks"][0]["config"]["serviceId"] == "ai4bharat/conformer-en"
            assert body["pipelineTasks"][0]["config"]["audioFormat"] == "wav"
            # Verify base64 audio content
            raw_b64 = body["inputData"]["audio"][0]["audioContent"]
            assert base64.b64decode(raw_b64) == pcm_wav()
            return httpx.Response(200, json=_make_asr_compute_response("I have severe chest pain"))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    settings = BhashiniSettings(
        api_key=SecretStr("key-123"),
        user_id=SecretStr("user-456"),
    )
    provider = BhashiniSpeechProvider(settings=settings, transport=transport)

    result = await provider.transcribe(
        audio=pcm_wav(),
        language="en",
        media_type="audio/wav",
    )

    assert isinstance(result, TranscriptionResult)
    assert result.status == "success"
    assert result.transcript == "I have severe chest pain"
    assert result.language == "en"
    assert result.confidence is None
    assert result.provider == "bhashini"
    assert result.model == "ai4bharat/conformer-en"
    assert len(calls) == 2


@pytest.mark.anyio
async def test_bhashini_transcribe_bn_and_cache():
    discovery_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal discovery_count
        url_str = str(request.url)
        if "/getModelsPipeline" in url_str:
            discovery_count += 1
            return httpx.Response(200, json=_make_discovery_response("asr", "bn", "ai4bharat/conformer-bn"))
        elif "/services/inference/pipeline" in url_str:
            return httpx.Response(200, json=_make_asr_compute_response("আমার বুকে চাপ লাগছে"))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    settings = BhashiniSettings(api_key=SecretStr("k"), user_id=SecretStr("u"))
    provider = BhashiniSpeechProvider(settings=settings, transport=transport)

    # First call - triggers discovery
    res1 = await provider.transcribe(pcm_wav(), "bn", "audio/wav")
    assert res1.status == "success"
    assert res1.transcript == "আমার বুকে চাপ লাগছে"
    assert res1.language == "bn"
    assert discovery_count == 1

    # Second call for bn - uses cached pipeline task config!
    res2 = await provider.transcribe(pcm_wav(), "bn", "audio/wav")
    assert res2.status == "success"
    assert res2.transcript == "আমার বুকে চাপ লাগছে"
    assert discovery_count == 1  # No second discovery!


@pytest.mark.anyio
async def test_bhashini_transcribe_hi():
    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "/getModelsPipeline" in url_str:
            return httpx.Response(200, json=_make_discovery_response("asr", "hi", "ai4bharat/conformer-hi"))
        elif "/services/inference/pipeline" in url_str:
            return httpx.Response(200, json=_make_asr_compute_response("मुझे बहुत तेज सिरदर्द है"))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    settings = BhashiniSettings(api_key=SecretStr("k"), user_id=SecretStr("u"))
    provider = BhashiniSpeechProvider(settings=settings, transport=transport)

    res = await provider.transcribe(pcm_wav(), "hi", "audio/wav")
    assert res.status == "success"
    assert res.transcript == "मुझे बहुत तेज सिरदर्द है"
    assert res.language == "hi"


# -----------------------------------------------------------------------------
# 5. Direct Inference Mode (Pre-Configured URL)
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_bhashini_direct_inference_mode():
    called_urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        called_urls.append(str(request.url))
        assert request.headers["Authorization"] == "direct-token-999"
        return httpx.Response(200, json=_make_asr_compute_response("direct inference text"))

    transport = httpx.MockTransport(handler)
    settings = BhashiniSettings(
        api_key=SecretStr("k"),
        user_id=SecretStr("u"),
        inference_url="https://direct.dhruva.ai/v1/asr",
        inference_api_key=SecretStr("direct-token-999"),
    )
    provider = BhashiniSpeechProvider(settings=settings, transport=transport)

    res = await provider.transcribe(pcm_wav(), "en", "audio/wav")
    assert res.status == "success"
    assert res.transcript == "direct inference text"
    # Discovery was bypassed
    assert len(called_urls) == 1
    assert called_urls[0] == "https://direct.dhruva.ai/v1/asr"


# -----------------------------------------------------------------------------
# 6. TTS Question Synthesis
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_bhashini_synthesize_success():
    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "/getModelsPipeline" in url_str:
            body = json.loads(request.content.decode("utf-8"))
            assert body["pipelineTasks"][0]["taskType"] == "tts"
            return httpx.Response(200, json=_make_discovery_response("tts", "bn", "ai4bharat/indic-tts-bn"))
        elif "/services/inference/pipeline" in url_str:
            body = json.loads(request.content.decode("utf-8"))
            assert body["pipelineTasks"][0]["taskType"] == "tts"
            assert body["inputData"]["input"][0]["source"] == "আপনার বুকে ব্যথা কোথায় হচ্ছে?"
            return httpx.Response(200, json=_make_tts_compute_response(base64.b64encode(pcm_wav()).decode(), "wav"))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    settings = BhashiniSettings(api_key=SecretStr("k"), user_id=SecretStr("u"))
    provider = BhashiniSpeechProvider(settings=settings, transport=transport)

    result = await provider.synthesize(
        text="আপনার বুকে ব্যথা কোথায় হচ্ছে?",
        language="bn",
    )

    assert isinstance(result, SpeechSynthesisResult)
    assert result.status == "success"
    assert result.audio_base64 == base64.b64encode(pcm_wav()).decode()
    assert result.media_type == "audio/wav"
    assert result.language == "bn"
    assert result.text == "আপনার বুকে ব্যথা কোথায় হচ্ছে?"


@pytest.mark.anyio
async def test_bhashini_synthesize_empty_text():
    provider = BhashiniSpeechProvider(
        settings=BhashiniSettings(api_key=SecretStr("k"), user_id=SecretStr("u"))
    )
    res = await provider.synthesize(text="   ", language="en")
    assert res.status == "unavailable"
    assert res.reason == "empty_text"
    assert res.audio_base64 is None


# -----------------------------------------------------------------------------
# 7. Error Handling & Failure Resistance
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_bhashini_unsupported_language():
    provider = BhashiniSpeechProvider(
        settings=BhashiniSettings(api_key=SecretStr("k"), user_id=SecretStr("u"))
    )
    res = await provider.transcribe(pcm_wav(), "fr", "audio/wav")
    assert res.status == "unavailable"
    assert res.reason == "unsupported_language"


@pytest.mark.anyio
async def test_bhashini_empty_audio():
    provider = BhashiniSpeechProvider(
        settings=BhashiniSettings(api_key=SecretStr("k"), user_id=SecretStr("u"))
    )
    res = await provider.transcribe(b"", "en", "audio/wav")
    assert res.status == "unavailable"
    assert res.reason == "empty_audio"


@pytest.mark.anyio
async def test_bhashini_timeout_handling():
    def handler(request: httpx.Request):
        raise httpx.ReadTimeout("Read timed out after 15s")

    transport = httpx.MockTransport(handler)
    provider = BhashiniSpeechProvider(
        settings=BhashiniSettings(api_key=SecretStr("k"), user_id=SecretStr("u")),
        transport=transport,
    )

    res = await provider.transcribe(pcm_wav(), "en", "audio/wav")
    assert res.status == "unavailable"
    assert res.reason == "timeout"
    assert res.transcript is None


@pytest.mark.anyio
async def test_bhashini_auth_error():
    def handler(request: httpx.Request):
        return httpx.Response(401, json={"message": "Invalid API Key"})

    transport = httpx.MockTransport(handler)
    provider = BhashiniSpeechProvider(
        settings=BhashiniSettings(api_key=SecretStr("k"), user_id=SecretStr("u")),
        transport=transport,
    )

    res = await provider.transcribe(pcm_wav(), "en", "audio/wav")
    assert res.status == "unavailable"
    assert res.reason == "authentication_failed"


@pytest.mark.anyio
async def test_bhashini_rate_limited():
    def handler(request: httpx.Request):
        return httpx.Response(429, json={"message": "Rate limit exceeded"})

    transport = httpx.MockTransport(handler)
    provider = BhashiniSpeechProvider(
        settings=BhashiniSettings(api_key=SecretStr("k"), user_id=SecretStr("u")),
        transport=transport,
    )

    res = await provider.transcribe(pcm_wav(), "en", "audio/wav")
    assert res.status == "unavailable"
    assert res.reason == "rate_limited"


@pytest.mark.anyio
async def test_bhashini_upstream_500_error():
    def handler(request: httpx.Request):
        return httpx.Response(502, text="Bad Gateway")

    transport = httpx.MockTransport(handler)
    provider = BhashiniSpeechProvider(
        settings=BhashiniSettings(api_key=SecretStr("k"), user_id=SecretStr("u")),
        transport=transport,
    )

    res = await provider.transcribe(pcm_wav(), "en", "audio/wav")
    assert res.status == "unavailable"
    assert res.reason == "provider_error"


@pytest.mark.anyio
async def test_bhashini_invalid_json():
    def handler(request: httpx.Request):
        return httpx.Response(200, text="NOT_JSON_BODY")

    transport = httpx.MockTransport(handler)
    provider = BhashiniSpeechProvider(
        settings=BhashiniSettings(api_key=SecretStr("k"), user_id=SecretStr("u")),
        transport=transport,
    )

    res = await provider.transcribe(pcm_wav(), "en", "audio/wav")
    assert res.status == "unavailable"
    assert res.reason == "invalid_response"


# -----------------------------------------------------------------------------
# 8. Full FastAPI Endpoint Integration with Candidate Gate
# -----------------------------------------------------------------------------

def test_transcribe_endpoint_with_bhashini_provider(client, monkeypatch):
    monkeypatch.setenv("SPEECH_PROVIDER", "bhashini")
    monkeypatch.setenv("BHASHINI_API_KEY", "test-key")
    monkeypatch.setenv("BHASHINI_USER_ID", "test-user")

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "/getModelsPipeline" in url_str:
            return httpx.Response(200, json=_make_discovery_response("asr", "en", "bhashini/indic-asr"))
        elif "/services/inference/pipeline" in url_str:
            return httpx.Response(200, json=_make_asr_compute_response("chest pressure and heaviness"))
        return httpx.Response(404)

    mock_transport = httpx.MockTransport(handler)

    # Monkeypatch the provider factory to use our mock transport
    real_settings = BhashiniSettings.from_environment()
    mocked_provider = BhashiniSpeechProvider(settings=real_settings, transport=mock_transport)
    monkeypatch.setattr("app.services.speech.get_speech_provider", lambda: mocked_provider)

    # 1. Setup Session with Voice Consent
    session_id = str(uuid.uuid4())
    create_res = client.post(
        "/api/sessions",
        json={
            "id": session_id,
            "patient": {"name": "Test Patient", "demo_abha_id": None},
            "hospital_token": f"TEST-{session_id[:6]}",
            "language": "en",
        },
    )
    assert create_res.status_code == 201

    consent_res = client.put(
        f"/api/sessions/{session_id}/consent",
        json={
            "voice_processing": True,
            "document_processing": False,
            "share_with_doctor": True,
        },
    )
    assert consent_res.status_code == 200

    flow_res = client.put(
        f"/api/sessions/{session_id}/interview/flow",
        json={"flow_id": "chest_pain"},
    )
    assert flow_res.status_code == 200

    # 2. Transcribe via Bhashini
    fake_audio = io.BytesIO(pcm_wav())
    response = client.post(
        f"/api/sessions/{session_id}/interview/speech/transcribe",
        files={"audio": ("audio.webm", fake_audio, "audio/wav")},
        data={"question_id": "chief_complaint.description"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["transcript"] == "chest pressure and heaviness"
    assert data["provider"] == "bhashini"
    assert data["confidence"] is None

    # 3. Clinical Invariant Check: Transcribe MUST NOT persist an answer
    state = client.get(f"/api/sessions/{session_id}/interview").json()
    assert len(state["active_answers"]) == 0
    assert state["question"]["question_id"] == "chief_complaint.description"
