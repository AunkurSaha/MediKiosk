# Phase 4A Implementation and Verification Report — 2026-09-09

## Executive Summary

Phase 4A implements the complete **Provider-Neutral Voice Input and Text-To-Speech (TTS) Architecture** for MediKiosk.

The implementation establishes a robust speech boundary using deterministic mock providers first (`MockSpeechProvider`, `DisabledSpeechProvider`), strictly deferring external vendor APIs (BHASHINI, AI4Bharat) to Phase 4B.

The core architectural invariant is strictly preserved: **The deterministic `InterviewEngine` remains the sole clinical authority.** Speech providers never choose questions, alter branching, submit answers automatically, normalize clinical concepts, diagnose, prescribe, or trigger red flags.

All automated acceptance criteria (backend tests on PostgreSQL and SQLite, frontend component tests, ESLint/Prettier/TypeScript checks, Playwright browser E2E tests, and real process restart persistence) pass with 100% success.

---

## 1. Speech Architecture

The speech architecture establishes a provider-neutral boundary decoupling frontend recording and question playback from specific speech vendors:

```text
PATIENT VOICE RECORDING WORKFLOW:
Browser Microphone
    ↓
MediaRecorder API (WebM/Opus or browser default)
    ↓
POST /api/sessions/{session_id}/interview/speech/transcribe (multipart audio)
    ├── Precondition Check: session active, editable, share_with_doctor == true
    ├── Consent Check: voice_processing == true (HTTP 403 if false)
    ├── Validation: MIME allowlist, non-empty, 5MB file size cap
    ├── Ephemeral Audio: server-generated temp file unlinked in finally block
    ↓
SpeechService → SpeechProvider Protocol
    ├── mock: MockSpeechProvider (deterministic fixtures + fallback canonical transcripts)
    ├── disabled: DisabledSpeechProvider
    └── future: BhashiniSpeechProvider (Phase 4B)
    ↓
TranscriptionResult (candidate transcript, null confidence, provider metadata)
    ↓
Candidate Review Card ("You said: ...")
    ├── [ Confirm ]      → POST /interview/answers (source: 'voice')
    ├── [ Edit ]         → inline edit → POST /interview/answers (source: 'typed')
    ├── [ Record again ] → re-record
    └── [ Cancel ]       → dismiss candidate
    ↓
Standard Answer Persistence & History Update (InterviewEngine)
    ↓
Phase 3 Clinical Normalization Pipeline (downstream only)
    ↓
Next Question Chosen Deterministically

QUESTION TEXT-TO-SPEECH (TTS) WORKFLOW:
Patient presses [ Listen ] / [ শুনুন ] / [ सुनें ]
    ↓
POST /api/sessions/{session_id}/interview/speech/synthesize
    ├── Pinned complaint flow snapshot provides EXACT localized question text
    ├── Patient answers, clinical histories, and summaries are strictly excluded
    ↓
SpeechService → SpeechProvider Protocol
    ↓
SpeechSynthesisResult (base64 audio payload + MIME type)
    ↓
Browser Audio Playback
```

### Components Implemented:
- **`backend/app/services/speech_provider.py`**:
  - `SpeechProvider` Protocol defining `transcribe(...) -> TranscriptionResult` and `synthesize(...) -> SpeechSynthesisResult`.
  - `MockSpeechProvider`: Deterministic transcription supporting English (`en`), Bengali (`bn`), and Hindi (`hi`). Matches known audio fixtures (e.g. `chest_pain_en.webm` → `"I have chest pain"`, `chest_pain_bn.webm` → `"আমার বুকে ব্যথা হচ্ছে"`, `chest_pain_hi.webm` → `"मुझे सीने में दर्द हो रहा है"`) and falls back to canonical concepts (`"chest pain"`, `"বুকে ব্যথা"`, `"सीने में दर्द"`). Generates minimal valid 8kHz mono WAV audio for deterministic playback tests.
  - `DisabledSpeechProvider`: Cleanly returns `status: unavailable`, `reason: speech_disabled`.
- **`backend/app/services/speech.py`**:
  - `transcribe_audio(...)`: Enforces 5MB size limit, validates MIME types, checks session editability and `voice_processing` consent, creates server-side ephemeral temp files, and guarantees deletion via `try...finally: unlink()`.
  - `synthesize_question(...)`: Loads the session's pinned flow snapshot and extracts strictly the localized question text matching the session language.
- **`backend/app/schemas/speech.py`**:
  - `TranscriptionResult`: Strict schema with `transcript`, `language`, `confidence` (must be `null` when provider does not expose calibrated confidence), `provider`, `model`, `status`, and `reason`.
  - `SpeechSynthesisRequest` & `SpeechSynthesisResult`: Strict synthesis schemas.
- **`backend/app/core/config.py`**:
  - Added `SPEECH_PROVIDER` setting (`mock`, `disabled`, default `mock`).
  - Added startup validation in lifespan context (`validate_speech_configuration()`).

---

## 2. Frontend MediaRecorder Implementation

The frontend implementation uses the browser-native `MediaRecorder` API:
- **Component**: `frontend/src/components/kiosk/VoiceRecorder.tsx`
- **Capability Check**: Detects presence of `navigator.mediaDevices?.getUserMedia` and `window.MediaRecorder`. If missing, cleanly displays an informative fallback message.
- **Permission Handling**: Catches `NotAllowedError` or permission denial and displays a clear localized alert: `"Microphone access was denied. Please use the keyboard or touch controls."`
- **MIME Format Negotiation**: Prefers `audio/webm;codecs=opus`, then `audio/webm`, then `audio/ogg`, falling back to browser default.
- **Visual Feedback**:
  - Idle state: Clear microphone trigger button ("Record answer" / "উত্তর বলুন" / "बोलकर उत्तर दें").
  - Recording state: High-visibility pulsing red indicator, elapsed timer (`0:03`), and explicit `Done` and `Cancel` buttons.
  - Uploading state: Spinner indicating audio processing.
- **Ephemeral In-Memory Handling**: Audio chunks are collected in an in-memory array during recording, converted to a single Blob on stop, and transmitted. Memory references and object URLs are cleared immediately upon submission or cancellation. No audio blobs are written to `localStorage`, `sessionStorage`, or `IndexedDB`.
- **Touch/Type Preservation**: The typed/touch answer control is always visible directly below the voice control. Voice is strictly an adjunct input method.

---

## 3. Audio Format & Resource Limits

| Attribute | Specification | Enforcement |
|---|---|---|
| Maximum File Size | 5MB (`5 * 1024 * 1024` bytes) | Backend HTTP 413 `FILE_TOO_LARGE` |
| Minimum File Size | > 0 bytes (non-empty) | Backend HTTP 422 `EMPTY_AUDIO` |
| Supported MIME Types | `audio/webm`, `audio/ogg`, `audio/wav`, `audio/mp4`, `audio/mpeg` | Backend HTTP 415 `UNSUPPORTED_MEDIA_TYPE` |
| Destination Filename | Server-generated random UUID (`uuid.uuid4()`) | Client filename is completely ignored |
| Storage Location | System temporary directory (`tempfile.gettempdir()`) | Never written to database, object store, or project tree |
| Maximum Recording Duration | Kiosk UI displays elapsed timer; prototype enforces 5MB cap | Prototype limit |

---

## 4. ASR Endpoint Specification

- **Endpoint**: `POST /api/sessions/{session_id}/interview/speech/transcribe`
- **Request**: Multipart form data with `audio` file and optional `language`.
- **Precondition Validations**:
  1. Session exists and is active (`ready_for_review == false`, `is_confirmed == false`).
  2. Sharing consent (`share_with_doctor == true`) is granted.
  3. Voice consent (`voice_processing == true`) is granted (returns HTTP 403 `VOICE_CONSENT_REQUIRED` if false).
  4. Audio payload is non-empty and <= 5MB.
  5. Audio MIME type is in supported allowlist.
- **Execution**: Streams audio bytes to ephemeral temporary file, invokes `SpeechService.transcribe()`, unlinks file in `finally` block, and returns `TranscriptionResult`.
- **State Invariance**: **Crucially, this endpoint does NOT mutate interview answers or progress.** The returned transcript is strictly a candidate.

---

## 5. Candidate Confirmation Workflow

ASR output is never treated as clinical fact without explicit patient confirmation:

1. **Candidate Display**: When transcription completes, the kiosk presents the **Candidate Review Card**:
   - English: `"You said:"`
   - Bengali: `"আপনি বলেছেন:"`
   - Hindi: `"आपने कहा:"`
2. **Action Controls**:
   - **Confirm**: Submits the transcript directly via `POST /api/sessions/{session_id}/interview/answers` with `source: 'voice'`.
   - **Edit**: Replaces the review card with an inline text area pre-filled with the candidate text. The patient edits their words and clicks `Save`, submitting via `POST /interview/answers` with `source: 'typed'`.
   - **Record again**: Clears the candidate transcript and immediately re-arms the microphone recorder.
   - **Cancel**: Dismisses the candidate review card and restores the idle voice button without submitting anything.
3. **Convergence**: Once confirmed, the answer converges into the exact same interview answer pathway as typed answers, advancing the deterministic `InterviewEngine` and triggering downstream clinical normalization.

---

## 6. Source Provenance Behavior

| Action Taken by Patient | Persisted `source` | Clinical Wording Preserved |
|---|---|---|
| Speaks → Confirms transcript directly | `source: 'voice'` | Exact candidate transcript |
| Speaks → Edits candidate text → Confirms | `source: 'typed'` | Exact patient-edited wording |
| Types directly into textarea | `source: 'typed'` | Exact patient-typed wording |
| Taps choice/duration/boolean button | `source: 'touch'` | Exact option/value representation |

This distinction ensures that human-authored revisions are never falsely recorded as machine ASR outputs.

---

## 7. Text-to-Speech (TTS) Architecture

- **Endpoint**: `POST /api/sessions/{session_id}/interview/speech/synthesize`
- **Request**: `{"question_id": "chief_complaint.description"}`
- **Safety Boundary**:
  - Synthesizes strictly the exact localized question text already approved in the session's pinned complaint flow snapshot (`InterviewRun.flow_snapshot`).
  - Prohibits sending clinical history, patient answers, doctor summaries, or PII to TTS.
- **Frontend Component**: `frontend/src/components/kiosk/QuestionAudioPlayer.tsx`
  - Rendered in the question header alongside the question text.
  - Buttons:
    - English: `🔊 Listen` / `🔊 Playing...`
    - Bengali: `🔊 শুনুন` / `🔊 বাজছে...`
    - Hindi: `🔊 सुनें` / `🔊 चल रहा है...`
  - Playback is strictly patient-initiated; auto-play is prohibited.
  - Playback errors display a localized retry button without blocking interview completion.

---

## 8. Consent Enforcement

- **Database & Schemas**: `Consent` model and schema updated with `voice_processing: bool = False`.
- **Intake Screen**: Consent screen (`/kiosk/consent`) features an explicit toggle for voice processing with a clear disclaimer: `"Process voice for spoken questions (audio is processed ephemerally and never permanently stored)"`.
- **Backend Gate**: Any request to `POST /interview/speech/transcribe` verifies `consent.voice_processing`. If false, returns HTTP 403 `VOICE_CONSENT_REQUIRED`.
- **Frontend Gate**: If `voice_processing` is false, the microphone recording button is completely hidden on interview questions.

---

## 9. Audio Deletion & Privacy Verification

A dedicated suite of adversarial tests in `backend/tests/test_speech.py` verified the ephemeral lifecycle:
- **Success Case**: Ephemeral temp file deleted immediately after transcription completes (`test_ephemeral_audio_deleted_on_success`).
- **Provider Error Case**: Ephemeral temp file deleted when the provider raises an exception (`test_ephemeral_audio_deleted_on_provider_error`).
- **Validation Rejection Case**: Temp file cleaned up on invalid MIME or oversized upload.
- **Database Verification**: Verified zero audio tables or columns exist in PostgreSQL.
- **Object Storage Verification**: Verified no audio files are written to MinIO/S3.

---

## 10. Automated Test Results

### Backend (`pytest`):
- **SQLite Profile**: **231 passed** in 10.80s (214 Phase 1/2/3A/3B regressions + 17 Phase 4A speech tests).
- **PostgreSQL Profile**: **231 passed** in 14.67s.

Key Backend Scenarios Covered:
- Mock transcription for English, Bengali, and Hindi with fixture matching and fallback.
- Voice consent required (HTTP 403 `VOICE_CONSENT_REQUIRED`).
- Completed/locked session rejection (HTTP 409 `SESSION_LOCKED`).
- Validation: unsupported MIME (HTTP 415), empty audio (HTTP 422), oversized file (HTTP 413), language mismatch (HTTP 400).
- Provider timeout/unavailability simulation.
- Transcription does not mutate interview state or persist answers.
- Confirmed transcript persists as `source: 'voice'`.
- Edited transcript persists as `source: 'typed'`.
- Downstream clinical normalization executes only after answer confirmation.
- Question TTS extracts strictly localized question text from pinned flow snapshot.

### Frontend Component Tests (`Vitest`):
- **Total**: **47 passed** across 4 test suites in 1.45s (36 regressions + 11 new speech tests).
- Covered:
  - `QuestionAudioPlayer`: idle, playing, audio loading, retry on error.
  - `VoiceRecorder`: browser support check, permission denied fallback, recording timer, candidate card display, confirm action, edit action with inline save, record again action, cancel action.
  - Multilingual label rendering for English, Bengali, and Hindi.

### Code Quality & Static Analysis:
- `npm run lint` (ESLint): **0 errors, 0 warnings**.
- `npm run build` (`tsc -b && vite build`): **Clean compilation, zero TypeScript errors**.
- `ruff check`: **Clean**.

---

## 11. Playwright Browser E2E Results

Five end-to-end browser scenarios were implemented in `frontend/e2e/speech.spec.ts` using a mocked browser `MediaRecorder` API to run deterministically in headless CI without physical microphones:

| Spec | Scenario | Result |
|---|---|---|
| `speech.spec.ts` | English Voice Journey: record → review candidate → confirm → persists `source: 'voice'` → normalization runs | **Passed** |
| `speech.spec.ts` | Bengali Voice Journey: Bengali intake → Bengali candidate review → confirm → persists | **Passed** |
| `speech.spec.ts` | Transcript Edit Journey: record → click Edit → modify text → confirm → persists `source: 'typed'` | **Passed** |
| `speech.spec.ts` | Fallback Journey: simulated ASR error → displays fallback banner → completes via typed answer | **Passed** |
| `speech.spec.ts` | TTS Playback Journey: question loaded → click Listen → verifies synthesize request & playback | **Passed** |
| Full E2E Suite | 12 tests across 5 spec files (`adaptive`, `intake`, `normalization`, `restart`, `speech`) | **12 passed** in 44.6s |

---

## 12. Database Continuity & Migrations

- **Migration Assessment**: The `interview_answers.source` column in PostgreSQL was already defined as an unconstrained `String` column in SQLAlchemy and Alembic. Expanding allowed sources to include `"voice"` required **zero database schema migrations**.
- **Data Preservation**: Pre-existing sessions, answers, normalization results, and doctor summaries from Phases 1, 2, 3A, and 3B remain 100% intact and unaltered.

---

## 13. Process Restart Persistence Verification

The automated restart verification script was executed:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-restart.ps1
```
- Real PostgreSQL process (`127.0.0.1:55432`) and FastAPI backend process (`127.0.0.1:8010`) were stopped and restarted with new PIDs.
- Verified that all historical records (legacy Phase 1 sessions, Phase 2 adaptive sessions, Phase 3A/3B normalized sessions, and Phase 4A speech sessions) survived the restart unchanged.
- Post-restart browser resume tests passed completely.

---

## 14. Adversarial Verification Findings

A secondary verification pass was conducted to search for edge-case vulnerabilities:

1. **Candidate Persistence Leak**: Verified that calling `/interview/speech/transcribe` ten consecutive times without calling `/interview/answers` creates zero `interview_answers` rows in PostgreSQL.
2. **Ephemeral File Cleanup**: Verified via Python filesystem checks that after simulating unhandled exceptions during transcription, zero temp files remain in `tempfile.gettempdir()`.
3. **Voice Consent Bypass**: Verified that attempting to transcribe audio on a session with `voice_processing = false` immediately aborts at the FastAPI route level before reading file contents into memory or writing to disk.
4. **Provenance Fidelity**: Verified in E2E tests that editing a candidate transcript prior to submission records `source: 'typed'` in PostgreSQL, while directly confirming records `source: 'voice'`.
5. **TTS Data Isolation**: Verified that the TTS synthesis route inspects only the pinned complaint flow snapshot; attempting to pass a question ID from another flow or unpinned question returns HTTP 404.
6. **Frontend State Warning Fix**: Identified and resolved a React `setState` during render warning in `QuestionAudioPlayer` when navigating between questions.

---

## 15. Known Limitations

1. **Mock Speech Implementation**: Phase 4A uses deterministic mock speech providers. Live cloud ASR/TTS via BHASHINI or AI4Bharat is scheduled for Phase 4B.
2. **Prototype File Size Limit**: Uploads are restricted to 5MB, which easily accommodates the typical 10-30 second spoken symptom description.
3. **Audio Playback in Headless CI**: Headless Chromium in CI lacks physical sound cards; TTS audio playback is verified via network request inspection and mocked HTML5 Audio APIs.

---

## 16. Files Changed in Phase 4A

### Backend:
- `backend/app/schemas/consent.py` (added `voice_processing: bool`)
- `backend/app/schemas/adaptive.py` (added `"voice"` to `source`)
- `backend/app/schemas/interview_answer.py` (added `"voice"` to `source`)
- `backend/app/schemas/speech.py` (new strict Pydantic schemas for ASR & TTS)
- `backend/app/core/config.py` (added `SPEECH_PROVIDER` configuration & startup validation)
- `backend/app/services/speech_provider.py` (new `SpeechProvider` protocol, `MockSpeechProvider`, `DisabledSpeechProvider`)
- `backend/app/services/speech.py` (new `SpeechService` with ephemeral file handling & TTS extraction)
- `backend/app/api/v1/speech.py` (new transcribe & synthesize FastAPI endpoints)
- `backend/app/api/v1/routers.py` (mounted speech router)
- `backend/app/main.py` (updated `/config` endpoint to report `phase: "4A"` and `speech_provider`)
- `backend/tests/test_speech.py` (17 comprehensive unit & integration tests)

### Frontend:
- `frontend/src/i18n/speech.ts` (multilingual localized copy for English, Bengali, Hindi)
- `frontend/src/api/interview.ts` (added `TranscriptionResponse`, `SpeechSynthesisResponse`, updated `Submission.source`)
- `frontend/src/api/client.ts` (added `transcribeSpeech`, `synthesizeSpeech`, updated `consent`)
- `frontend/src/components/kiosk/QuestionAudioPlayer.tsx` (new TTS playback component)
- `frontend/src/components/kiosk/VoiceRecorder.tsx` (new MediaRecorder & Candidate Review Card component)
- `frontend/src/components/kiosk/QuestionRenderer.tsx` (integrated audio player & voice recorder on `short_text` questions)
- `frontend/src/components/kiosk/Interview.tsx` (passed `voiceConsent` prop down to renderers)
- `frontend/src/routes/kiosk/index.tsx` (added voice consent checkbox and disclaimer)
- `frontend/src/index.css` (styles for pulse animations, candidate review cards, speaker buttons)
- `frontend/src/test/speech.test.tsx` (11 unit/component tests)
- `frontend/e2e/speech.spec.ts` (5 Playwright E2E tests)

### Documentation:
- `docs/decisions.md` (added ADR-018)
- `docs/architecture.md` (documented Phase 4A speech & TTS architecture)
- `docs/api-contract.md` (documented `/speech/transcribe` and `/speech/synthesize`)
- `docs/design.md` (documented VoiceRecorder, QuestionAudioPlayer, and Candidate Review Card UX)
- `docs/security-privacy.md` (documented zero raw audio retention, ephemeral temp files, consent gates)
- `docs/testing.md` (documented Phase 4A test coverage and acceptance criteria)
- `docs/roadmap.md` (updated status to Phase 4A completed; outlined Phase 4B)
- `docs/requirements-traceability.md` (updated traceability table and evidence)
- `docs/memory.md` (updated project memory with Phase 4A invariants)
- `docs/phase4a-implementation-status.md` (this comprehensive report)
- `docs/implementation-status.md` (updated summary status)

---

## 17. Recommendation for Phase 4B: BHASHINI Integration

For Phase 4B, connect the live Government of India **BHASHINI (ULCA)** Speech API behind the existing `SpeechProvider` interface:

1. **Create `BhashiniSpeechProvider`**:
   - Implement the `SpeechProvider` protocol in `backend/app/services/bhashini_speech.py`.
   - Store credentials securely: `BHASHINI_API_KEY`, `BHASHINI_USER_ID`, `BHASHINI_PIPELINE_ID` in environment variables wrapped in `SecretStr`.
2. **ASR Integration**:
   - Call the BHASHINI ULCA Pipeline API (`/ulca/apis/v0/model/getModelsPipeline` & compute endpoint).
   - If BHASHINI requires WAV/PCM, incorporate a lightweight transcoding step using `ffmpeg` or Python `wave` module for WebM → WAV conversion.
   - Map returned ASR text to `TranscriptionResult`.
3. **TTS Integration**:
   - Call BHASHINI TTS service passing the exact localized question text.
   - Return base64-encoded MP3/WAV payload to the frontend.
4. **Preserve Architectural Invariants**:
   - The candidate confirmation workflow, ephemeral audio deletion, voice consent check, and InterviewEngine authority must remain identical to Phase 4A.
   - Fallback to mock provider should remain supported for offline development and CI.
