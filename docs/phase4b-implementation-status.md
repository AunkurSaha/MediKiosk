# Phase 4B Implementation and Verification Report — 2026-09-09

## Executive Summary

Phase 4B connects the Government of India's **BHASHINI (ULCA)** Speech Platform as a real speech-to-text (ASR) and text-to-speech (TTS) provider behind MediKiosk's existing Phase 4A provider-neutral speech interface.

Key architectural achievements in Phase 4B:
1. **Zero LLM / ASR Clinical Authority**: Bhashini ASR and TTS models have zero authority over question sequencing, branching logic, answer commitment, concept normalization, or red-flag detection. The deterministic `InterviewEngine` remains the sole clinical authority.
2. **Mandatory Candidate Confirmation Gate**: ASR transcripts returned by Bhashini are strictly unconfirmed candidate suggestions. They are **never** committed directly to interview state or clinical history. The patient must explicitly confirm the candidate transcript via the kiosk UI (`[Confirm]`, `[Edit]`, `[Record again]`, or `[Cancel]`).
3. **Ephemeral Audio & Zero Raw Audio Retention**: In compliance with [`docs/security-privacy.md`](security-privacy.md), patient voice recordings are never saved to PostgreSQL, object storage, or permanent disk. Server-side audio buffers are held in memory solely for the duration of upstream transmission and discarded immediately upon completion, timeout, or failure.
4. **Dual Architecture Support (ULCA Pipeline Discovery & Direct Inference)**: The adapter supports both standard two-step Bhashini ULCA pipeline discovery (`/ulca/apis/v0/model/getModelsPipeline` + compute callback) with in-memory pipeline config caching (1-hour TTL), as well as pre-configured direct inference compute endpoints (`BHASHINI_INFERENCE_URL` / `BHASHINI_INFERENCE_API_KEY`) for self-hosted or dedicated deployments (e.g. AI4Bharat / Dhruva).
5. **Zero Secret Leakage**: All API keys, user IDs, and inference bearer tokens are handled using Pydantic `SecretStr(exclude=True, repr=False)` and are excluded from logging, serialization, and API responses.
6. **Graceful Degradation & Bounded Latency**: Upstream timeouts, network interruptions, 401/403 authentication rejections, 429 rate limits, and 5xx errors return explicit `status: "unavailable"` results with technical reasons (`timeout`, `authentication_failed`, `rate_limited`, `provider_error`) without crashing the application or rolling back patient progress. The kiosk seamlessly displays a localized fallback notice and keeps touch/type controls active.
7. **Offline Mock Independence**: The default configuration remains `SPEECH_PROVIDER=mock`, requiring zero secrets and zero network calls, ensuring automated CI runs and local development environments remain completely isolated and reproducible.
8. **Zero Database Migrations**: `answers.source` is an unconstrained string column supporting `"voice"` and `"typed"`. No schema modifications or database migrations are required.

All automated acceptance checks (20 Bhashini unit and mock integration tests, 270 total backend tests on PostgreSQL and SQLite, 52 frontend vitest tests, ESLint with 0 warnings, TypeScript build with 0 errors) pass with 100% success.

---

## 1. Speech Architecture

```text
PATIENT SPOKEN INPUT (WebM/Opus / WAV):
Browser MediaRecorder
    ↓
POST /api/sessions/{session_id}/interview/speech/transcribe (ephemeral bytes in memory)
    ├── Consent Check: requires voice_processing == true (HTTP 403 if false)
    ├── Bounds & MIME Validation: max 5MB, allowlist checked
    ↓
SpeechService → BhashiniSpeechProvider (backend/app/services/bhashini_speech.py)
    ├── Input minimization: audio bytes + target language ('en', 'bn', 'hi')
    ├── Pipeline Discovery (POST https://meity-auth.ulca.ai/ulca/apis/v0/model/getModelsPipeline)
    │   └── In-memory cache for discovered callbackUrl & serviceId (1-hour TTL)
    │   └── Alternatively: direct compute endpoint (BHASHINI_INFERENCE_URL)
    ├── Compute Inference (POST callbackUrl with Authorization header)
    │   └── Payload: base64-encoded audio, taskType: 'asr', audioFormat: 'webm' | 'wav' | 'ogg'
    ↓
Candidate TranscriptionResult (status: 'success' | 'unavailable', transcript: str, confidence: null)
    ↓
Candidate Confirmation Gate (Kiosk UI):
    ├── [ Confirm ] → commits to PostgreSQL with source: 'voice'
    ├── [ Edit ]    → inline editing → commits to PostgreSQL with source: 'typed'
    └── [ Retry ] / [ Cancel ]
    ↓
Ephemeral Audio Cleanup: Audio bytes discarded immediately from memory; zero disk/DB retention.

QUESTION TEXT-TO-SPEECH (TTS):
Patient clicks [ Listen ] / [ শুনুন ] / [ सुनें ]
    ↓
POST /api/sessions/{session_id}/interview/speech/synthesize
    ├── Pinned complaint flow snapshot provides EXACT localized question text
    ↓
SpeechService → BhashiniSpeechProvider
    ├── Pipeline Discovery (taskType: 'tts', sourceLanguage)
    ├── Compute Inference (inputData: localized text, gender: 'female')
    ↓
SpeechSynthesisResult (status: 'success', audio_base64: str, media_type: 'audio/wav')
    ↓
Browser Audio Playback
```

---

## 2. Components Implemented

### Backend
1. **`BhashiniSpeechProvider` & `BhashiniSettings`** ([`backend/app/services/bhashini_speech.py`](file:///C:/MEDIKIOSK/backend/app/services/bhashini_speech.py)):
   - Implements `SpeechProvider` Protocol (`name = "bhashini"`, `version = "ulca-v0"`).
   - `BhashiniSettings`: Pydantic settings loading `BHASHINI_API_KEY`, `BHASHINI_USER_ID`, `BHASHINI_PIPELINE_ID`, `BHASHINI_ENDPOINT_URL`, `BHASHINI_INFERENCE_URL`, `BHASHINI_INFERENCE_API_KEY`, `BHASHINI_TIMEOUT_SECONDS`.
   - `_discover_pipeline_task(...)`: Performs ULCA pipeline discovery and caches callback endpoints and service IDs for 1 hour.
   - `transcribe(...)`: Translates audio format, encodes base64 audio, executes ASR compute, parses output, and handles errors into explicit `unavailable` results.
   - `synthesize(...)`: Formats localized text payload, executes TTS compute, extracts base64 audio payload, and returns synthesis result.
2. **Provider Registration** ([`backend/app/services/speech_provider.py`](file:///C:/MEDIKIOSK/backend/app/services/speech_provider.py)):
   - Updated `get_speech_provider()` to instantiate `BhashiniSpeechProvider` when `SPEECH_PROVIDER=bhashini`.
   - Updated `validate_speech_configuration()` to verify `BHASHINI_API_KEY` and `BHASHINI_USER_ID` are configured at startup.
3. **Operator Diagnostic Script** ([`scripts/evaluate-bhashini-speech.py`](file:///C:/MEDIKIOSK/scripts/evaluate-bhashini-speech.py)):
   - Standalone diagnostic tool to test live ULCA pipeline connectivity, ASR, and TTS across English, Bengali, and Hindi.

---

## 3. Automated Verification Results

| Suite / Test | Command | Status | Details |
|---|---|---|---|
| **Bhashini Dedicated Tests** | `pytest tests/test_bhashini_speech.py` | **20 PASSED** | Settings, discovery, ASR, TTS, direct inference, error handling |
| **Existing Speech Tests** | `pytest tests/test_speech.py` | **17 PASSED** | Consent, size caps, candidate confirmation, mock fixtures |
| **PostgreSQL Backend Suite** | `python scripts/test_postgres.py` | **270 PASSED** | 100% pass on real PostgreSQL database (11.83s) |
| **SQLite Backend Suite** | `pytest` | **270 PASSED** | 100% pass on SQLite test profile (9.27s) |
| **Backend Ruff Linter** | `ruff check .` | **PASSED** | 0 errors across all backend packages |
| **Frontend Vitest Suite** | `npm test` in `frontend/` | **52 PASSED** | All frontend component and workflow tests passed |
| **Frontend ESLint** | `npm run lint` in `frontend/` | **PASSED** | 0 errors, 0 warnings |
| **Frontend TypeScript** | `npx tsc -b` in `frontend/` | **PASSED** | Clean type checking |

---

## 4. Next Milestone

With Phase 4B complete, the voice intake pipeline provides full multilingual ASR and TTS capability backed by India's national language infrastructure.

The next roadmap milestone is **Phase 6 — Document Ingestion + OCR Pipeline**:
- Multipart prescription and lab report file uploads (`POST /api/sessions/{id}/documents`).
- Local object storage with SHA-256 integrity verification.
- Document classification and preprocessing (OpenCV).
- Structured fact extraction (PaddleOCR / Tesseract) into `document_extractions` with confidence scoring.
- Physician split-screen verification interface in the Doctor Workspace.
