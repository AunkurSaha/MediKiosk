import asyncio
import base64
import struct
from types import SimpleNamespace

import pytest

from app.services.sarvam_speech import SarvamSettings, SarvamSpeechProvider


def _wav(sample_rate: int = 16000, channels: int = 1, width: int = 2) -> bytes:
    frames = b"\x00" * (160 * channels * width)
    byte_rate = sample_rate * channels * width
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(frames),
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        byte_rate,
        channels * width,
        width * 8,
        b"data",
        len(frames),
    ) + frames


class _SpeechToText:
    def __init__(self, response=None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.kwargs = None

    async def transcribe(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.response


class _TextToSpeech:
    def __init__(self, response=None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.kwargs = None

    async def convert(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.response


class _Client:
    def __init__(self, transcript="বুকে ব্যথা", audio: str | None = None):
        self.speech_to_text = _SpeechToText(SimpleNamespace(transcript=transcript))
        self.text_to_speech = _TextToSpeech(
            SimpleNamespace(audios=[audio or base64.b64encode(_wav()).decode("ascii")])
        )


def _provider(client: _Client) -> SarvamSpeechProvider:
    return SarvamSpeechProvider(
        SarvamSettings(api_key="synthetic-key"),
        client_factory=lambda **_kwargs: client,
    )


def test_settings_read_key_without_exposing_it(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "synthetic-secret")
    settings = SarvamSettings.from_environment()
    assert settings.api_key.get_secret_value() == "synthetic-secret"
    assert "synthetic-secret" not in repr(settings)
    assert "api_key" not in settings.model_dump()


@pytest.mark.parametrize(
    ("rate", "channels", "width"), [(8000, 1, 2), (16000, 2, 2), (16000, 1, 1)]
)
def test_transcribe_rejects_non_16k_mono_pcm16(rate, channels, width):
    client = _Client()
    result = asyncio.run(_provider(client).transcribe(_wav(rate, channels, width), "en", "audio/wav"))
    assert result.status == "unavailable"
    assert result.reason == "unsupported_audio_format"
    assert client.speech_to_text.kwargs is None


def test_transcribe_uses_pinned_sdk_contract_without_retries():
    client = _Client()
    result = asyncio.run(_provider(client).transcribe(_wav(), "bn", "audio/wav"))
    assert result.status == "success"
    assert result.transcript == "বুকে ব্যথা"
    assert result.confidence is None
    args = client.speech_to_text.kwargs
    assert args["model"] == "saaras:v3"
    assert args["mode"] == "transcribe"
    assert args["language_code"] == "bn-IN"
    assert args["input_audio_codec"] == "wav"
    assert args["file"] == ("recording.wav", _wav(), "audio/wav")
    assert args["request_options"] == {"timeout_in_seconds": 12, "max_retries": 0}


def test_transcribe_maps_timeout_to_unavailable():
    client = _Client()
    client.speech_to_text = _SpeechToText(error=TimeoutError())
    result = asyncio.run(_provider(client).transcribe(_wav(), "hi", "audio/wav"))
    assert result.status == "unavailable"
    assert result.reason == "timeout"
    assert result.transcript is None


def test_synthesize_returns_provider_wav_and_exact_text():
    encoded = base64.b64encode(_wav()).decode("ascii")
    client = _Client(audio=encoded)
    result = asyncio.run(_provider(client).synthesize("আপনার প্রধান সমস্যা কী?", "bn"))
    assert result.status == "success"
    assert result.audio_base64 == encoded
    assert result.media_type == "audio/wav"
    assert result.text == "আপনার প্রধান সমস্যা কী?"
    args = client.text_to_speech.kwargs
    assert args["language_code"] == "bn-IN"
    assert args["model"] == "bulbul:v3"
    assert args["speaker"] == "shubh"
    assert args["speech_sample_rate"] == 16000
    assert args["output_audio_codec"] == "wav"
    assert args["request_options"]["max_retries"] == 0


def test_transcribe_all_supported_languages():
    for lang, code in [("bn", "bn-IN"), ("hi", "hi-IN"), ("en", "en-IN")]:
        client = _Client(transcript=f"transcript for {lang}")
        result = asyncio.run(_provider(client).transcribe(_wav(), lang, "audio/wav"))
        assert result.status == "success"
        assert result.transcript == f"transcript for {lang}"
        assert result.language == lang
        assert client.speech_to_text.kwargs["language_code"] == code


def test_transcribe_empty_or_whitespace_transcript():
    for empty_val in ["", "   ", "\n"]:
        client = _Client(transcript=empty_val)
        result = asyncio.run(_provider(client).transcribe(_wav(), "en", "audio/wav"))
        assert result.status == "unavailable"
        assert result.reason == "invalid_response"
        assert result.transcript is None


def test_transcribe_general_provider_error():
    client = _Client()
    client.speech_to_text = _SpeechToText(error=RuntimeError("Sarvam service connection failed"))
    result = asyncio.run(_provider(client).transcribe(_wav(), "bn", "audio/wav"))
    assert result.status == "unavailable"
    assert result.reason == "provider_error"
    assert result.transcript is None


def test_synthesize_all_supported_languages():
    for lang, code in [("bn", "bn-IN"), ("hi", "hi-IN"), ("en", "en-IN")]:
        encoded = base64.b64encode(_wav()).decode("ascii")
        client = _Client(audio=encoded)
        result = asyncio.run(_provider(client).synthesize(f"Hello in {lang}", lang))
        assert result.status == "success"
        assert result.audio_base64 == encoded
        assert result.language == lang
        assert client.text_to_speech.kwargs["language_code"] == code


def test_synthesize_empty_text():
    client = _Client()
    result = asyncio.run(_provider(client).synthesize("   ", "en"))
    assert result.status == "unavailable"
    assert result.reason == "empty_text"
    assert result.audio_base64 is None


def test_synthesize_timeout():
    client = _Client()
    client.text_to_speech = _TextToSpeech(error=TimeoutError())
    result = asyncio.run(_provider(client).synthesize("Hello", "en"))
    assert result.status == "unavailable"
    assert result.reason == "timeout"
    assert result.audio_base64 is None


def test_synthesize_rejects_invalid_provider_audio():
    client = _Client(audio="not-base64")
    result = asyncio.run(_provider(client).synthesize("Question", "en"))
    assert result.status == "unavailable"
    assert result.reason == "provider_error"
    assert result.audio_base64 is None

