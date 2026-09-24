import base64
import os
import struct
from typing import Any, Protocol

from app.schemas.speech import SpeechSynthesisResult, TranscriptionResult


def _create_minimal_wav_base64() -> str:
    """Generate a minimal valid 16-bit 8000Hz mono PCM WAV file containing 0.1s silence."""
    sample_rate = 8000
    num_channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    num_samples = int(sample_rate * 0.1)
    subchunk2_size = num_samples * block_align
    chunk_size = 36 + subchunk2_size

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        chunk_size,
        b"WAVE",
        b"fmt ",
        16,  # Subchunk1Size (16 for PCM)
        1,  # AudioFormat (1 for PCM)
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        subchunk2_size,
    )
    silence_data = b"\x00" * subchunk2_size
    return base64.b64encode(header + silence_data).decode("ascii")


MINIMAL_WAV_BASE64 = _create_minimal_wav_base64()


class SpeechProvider(Protocol):
    name: str
    version: str

    async def transcribe(
        self,
        audio: bytes,
        language: str,
        media_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> TranscriptionResult: ...

    async def synthesize(
        self,
        text: str,
        language: str,
    ) -> SpeechSynthesisResult: ...


MOCK_TRANSCRIPTS: dict[str, dict[str, str]] = {
    "default": {
        "en": "chest pain",
        "bn": "বুকে ব্যথা",
        "hi": "सीने में दर्द",
    },
    "chest_pain": {
        "en": "chest pain",
        "bn": "বুকে ব্যথা",
        "hi": "सीने में दर्द",
    },
    "chest_pain_sentence": {
        "en": "I have chest pain",
        "bn": "আমার বুকে ব্যথা হচ্ছে",
        "hi": "मुझे सीने में दर्द हो रहा है",
    },
    "headache": {
        "en": "headache",
        "bn": "মাথাব্যথা",
        "hi": "सिरदर्द",
    },
    "fever": {
        "en": "fever",
        "bn": "জ্বর",
        "hi": "बुखार",
    },
    "dyspnea": {
        "en": "shortness of breath",
        "bn": "শ্বাসকষ্ট",
        "hi": "सांस फूलना",
    },
    "negated_dyspnea": {
        "en": "I do not have shortness of breath",
        "bn": "আমার শ্বাসকষ্ট নেই",
        "hi": "मुझे सांस लेने में तकलीफ नहीं है",
    },
    "uncertain_pressure": {
        "en": "I think I sometimes have chest pressure",
        "bn": "মনে হয় মাঝে মাঝে বুক চাপ লাগে",
        "hi": "शायद कभी-कभी सीने में दबाव होता है",
    },
    "unknown": {
        "en": "I am waiting for the bus",
        "bn": "আমি বাসের জন্য অপেক্ষা করছি",
        "hi": "मैं बस का इंतज़ार कर रहा हूँ",
    },
}


class MockSpeechProvider:
    name: str = "mock"
    version: str = "mock-1.0"

    async def transcribe(
        self,
        audio: bytes,
        language: str,
        media_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> TranscriptionResult:
        meta = metadata or {}
        fixture_id = meta.get("fixture_id")

        if fixture_id == "simulate_timeout":
            return TranscriptionResult(
                status="unavailable",
                transcript=None,
                language=language,  # type: ignore[arg-type]
                confidence=None,
                provider=self.name,
                model=self.version,
                reason="timeout",
            )
        if fixture_id == "simulate_failure":
            return TranscriptionResult(
                status="unavailable",
                transcript=None,
                language=language,  # type: ignore[arg-type]
                confidence=None,
                provider=self.name,
                model=self.version,
                reason="provider_error",
            )

        fixtures = MOCK_TRANSCRIPTS.get(fixture_id or "default", MOCK_TRANSCRIPTS["default"])
        transcript = fixtures.get(language, fixtures.get("en", "I have chest pain"))

        return TranscriptionResult(
            status="success",
            transcript=transcript,
            language=language,  # type: ignore[arg-type]
            confidence=None,  # Strictly null for uncalibrated mock
            provider=self.name,
            model=self.version,
            reason=None,
        )

    async def synthesize(
        self,
        text: str,
        language: str,
    ) -> SpeechSynthesisResult:
        if not text.strip():
            return SpeechSynthesisResult(
                status="unavailable",
                audio_base64=None,
                media_type="audio/wav",
                text=text,
                language=language,  # type: ignore[arg-type]
                provider=self.name,
                reason="empty_text",
            )

        return SpeechSynthesisResult(
            status="success",
            audio_base64=MINIMAL_WAV_BASE64,
            media_type="audio/wav",
            text=text,
            language=language,  # type: ignore[arg-type]
            provider=self.name,
            reason=None,
        )


class DisabledSpeechProvider:
    name: str = "disabled"
    version: str = "disabled-1.0"

    async def transcribe(
        self,
        audio: bytes,
        language: str,
        media_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> TranscriptionResult:
        return TranscriptionResult(
            status="unavailable",
            transcript=None,
            language=language,  # type: ignore[arg-type]
            confidence=None,
            provider=self.name,
            model=self.version,
            reason="disabled",
        )

    async def synthesize(
        self,
        text: str,
        language: str,
    ) -> SpeechSynthesisResult:
        return SpeechSynthesisResult(
            status="unavailable",
            audio_base64=None,
            media_type="audio/wav",
            text=text,
            language=language,  # type: ignore[arg-type]
            provider=self.name,
            reason="disabled",
        )


_bhashini_instance = None
_sarvam_instance = None


def get_speech_provider() -> SpeechProvider:
    provider_name = os.getenv("SPEECH_PROVIDER", "mock").strip().lower()
    if provider_name == "mock":
        return MockSpeechProvider()
    if provider_name == "disabled":
        return DisabledSpeechProvider()
    if provider_name == "bhashini":
        global _bhashini_instance
        from app.services.bhashini_speech import BhashiniSettings, BhashiniSpeechProvider
        settings = BhashiniSettings.from_environment()
        if _bhashini_instance is None or _bhashini_instance.settings != settings:
            _bhashini_instance = BhashiniSpeechProvider(settings)
        return _bhashini_instance
    if provider_name == "sarvam":
        global _sarvam_instance
        from app.services.sarvam_speech import SarvamSettings, SarvamSpeechProvider

        settings = SarvamSettings.from_environment()
        if _sarvam_instance is None or _sarvam_instance.settings != settings:
            _sarvam_instance = SarvamSpeechProvider(settings)
        return _sarvam_instance
    raise RuntimeError(
        f"Unsupported SPEECH_PROVIDER: '{provider_name}'. "
        "Allowed: 'mock', 'disabled', 'bhashini', 'sarvam'."
    )


def validate_speech_configuration() -> None:
    provider = get_speech_provider()
    if provider.name == "bhashini":
        from app.services.bhashini_speech import BhashiniSettings
        settings = BhashiniSettings.from_environment()
        if settings.inference_api_key and settings.inference_api_key.get_secret_value():
            if not settings.asr_service_id or not settings.tts_service_id:
                raise RuntimeError(
                    "BHASHINI_ASR_SERVICE_ID and BHASHINI_TTS_SERVICE_ID are required "
                    "for direct SPEECH_PROVIDER=bhashini inference"
                )
            return
        if settings.inference_url:
            raise RuntimeError(
                "BHASHINI_INFERENCE_API_KEY or BHASHINI_INFERENCE_KEY is required "
                "when BHASHINI_INFERENCE_URL is configured"
            )
        if not settings.api_key.get_secret_value() or not settings.user_id.get_secret_value():
            raise RuntimeError(
                "BHASHINI_API_KEY and BHASHINI_USER_ID are required when SPEECH_PROVIDER=bhashini"
            )
    if provider.name == "sarvam":
        from app.services.sarvam_speech import SarvamSettings

        settings = SarvamSettings.from_environment()
        if not settings.api_key.get_secret_value():
            raise RuntimeError("SARVAM_API_KEY is required when SPEECH_PROVIDER=sarvam")

