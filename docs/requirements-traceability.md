# Requirements Traceability — MediKiosk

This keeps product promises tied to implementation phases and evidence.

| Requirement | Phase | Primary evidence |
|---|---:|---|
| Language selection | 1 | frontend test + demo |
| Demo patient identification | 1 | API/UI test |
| Granular consent | 1 | API/service test |
| Touch/type interview | 1 | E2E/API test |
| Doctor session review | 1 | E2E/API test |
| Doctor summary edit/confirm | 1 | API/UI test + audit assertion |
| Adaptive complaint flow | 2 — implemented | test_adaptive.py schema/engine/API tests; adaptive.spec.ts browser traversal |
| Five complaint families | 2 — implemented | Versioned authoritative JSON; all-flow completion/review parameterized tests |
| AYUSH demonstration mode | 2 — implemented | Isolated namespace validation; eleven-category traversal/review test |
| Clinical normalization boundary | 3A — implemented | 83 normalization tests, strict schema/fallback/provenance, PostgreSQL migration/restart |
| Real normalization provider | 3B — implemented | 55 contract/adversarial tests (test_nvidia_normalization.py), Schema 1.1 negation/uncertainty, SecretStr key audit, live diagnostic evaluation |
| Bengali/Hindi fixture normalization | 3A — implemented | Exact vocabulary tests and Bengali browser correction/doctor review; not broad NLP |
| Voice ASR | 4A — implemented | SpeechProvider protocol, MockSpeechProvider, 17 backend tests, candidate review card, E2E speech.spec.ts |
| TTS | 4A — implemented | QuestionAudioPlayer component, pinned flow question extraction, backend synthesis, E2E speech.spec.ts |
| Touch fallback for ASR failure | 4A — implemented | VoiceRecorder permission/unsupported/error fallback, component tests, E2E fallback test |
| Deterministic red flags | 5 | positive/negative rule tests |
| Triage alert dashboard | 5 | API/WebSocket/UI test |
| Document upload | 6 | API/storage integration test |
| Printed OCR | 6 | OCR fixtures |
| Confidence/provenance | 6 | extraction assertions |
| Medication/lab extraction | 7 | fixture tests |
| Timeline | 7 | ordering tests |
| Discrepancy detection | 7 | conflict fixture tests |
| AI draft summary | 8 | structured-output tests |
| Doctor verification hardening | 9 | version/audit tests |
| FHIR export | 10 | validation/fixture tests |
| ABDM/HIS demonstration | 11 | sandbox/mock evidence |
| Canonical Bengali chest-pain demo | 12 | scripted end-to-end demo |

## Rule

A feature is not “done” because a UI card exists. It should have at least one corresponding evidence item:
- automated test;
- validated integration response;
- clearly labelled mock;
- repeatable demo path.

## Phase 2 acceptance evidence

| Requirement | Evidence |
|---|---|
| Single backend flow authority | flow_registry startup validation; frontend duplicates removed |
| Version pinning | persisted flow snapshot; registry-change test; restart verification |
| Seven typed renderers | 7 parameterized frontend renderer tests; backend type/constraint matrix |
| Back/edit and branch safety | parent Yes/No/Yes API and browser tests; inactive facts excluded; historical rows retained |
| Raw wording and provenance | English whitespace/Bengali/Hindi roundtrips; correction IDs/sources retained |
| Durable retry safety | duplicate and delayed retry tests; stale revision guards; frontend request UUID reuse |
| Required/optional/unknown completion | explicit status tests, all-flow traversal and completion guards |
| Typed history and doctor review | ClinicalHistory snapshot equality; grouped doctor browser assertions; immutable confirmation regressions |
| Phase 1 preservation | all 19 original backend cases and 10 frontend regressions; legacy browser intake; migration fingerprints |
| Database continuity | empty/Phase 1 schema upgrades, actual app row fingerprint comparison, Alembic check, real process restart |
| Mobile/language/error states | en/bn/hi renderer tests, loading/retry/conflict tests, 390px Bengali browser screenshot |

## Phase 3A verified acceptance

- All 76 Phase 1/2 backend regressions remain passing; total 159 on SQLite and PostgreSQL.
- 83 new cases cover exact multilingual fixtures, unsupported/negated/contextual phrases, strict untrusted output, confidence/uncertainty, timeouts, unavailable/disabled provider, explicit field/type bypass, source edits, inactive history/reactivation, durable retries, savepoint failures and immutable confirmation.
- Doctor UI tests preserve raw Bengali wording and machine labels; total 33 frontend tests.
- Seven E2E tests pass; two browser resume checks pass after a real backend/PostgreSQL restart. Confirmed and in-progress normalization/provenance snapshots remain unchanged.
- Empty/Phase 1/Phase 2/actual-app migration checks preserve all existing rows and pass Alembic comparison.

## Phase 3B verified acceptance

- Total **214 backend tests** on each SQLite and PostgreSQL profile (all 159 Phase 1/2/3A regressions pass cleanly, plus 55 Phase 3B contract/adversarial tests).
- 55 new tests in `test_nvidia_normalization.py` cover:
  - Configuration loading, secret exclusion from Pydantic serialization/repr, invalid URL/model rejections without echo.
  - Input minimization: verifies context and patient identifiers are completely stripped.
  - Conservative sampling parameters: `temperature=0`, `stream=False`, `max_tokens=768`, `chat_template_kwargs={"enable_thinking": False}`.
  - Schema 1.1 domain outputs: explicit `polarity` (`present`/`absent`), `certainty` (`certain`/`uncertain`), `confidence: null`, exact evidence substring, and rejection of prohibited diagnostic/treatment fields.
  - Failure handling: timeouts, network errors, HTTP 401/403/429/500, truncated outputs, malformed JSON, and schema violations all record durable `unavailable` states.
  - Transaction isolation: raw patient answers commit safely regardless of normalization failure.
- Zero API key leakage confirmed by value-based audit across 156 files and logs.
- Database continuity confirmed: empty, Phase 1, Phase 2, Phase 3A, and real application DB upgrades preserve 100% of row counts and SHA-256 fingerprints with clean Alembic comparison.
- Empirical live evaluation documented: capability probe and opt-in synthetic evaluation test actual live interaction with `https://integrate.api.nvidia.com/v1` for `google/gemma-4-31b-it`.

## Phase 4A verified acceptance

- Total **231 backend tests** on each SQLite and PostgreSQL profile (all 214 Phase 1/2/3A/3B regressions pass cleanly, plus 17 new Phase 4A speech and TTS tests).
- 17 new backend tests in `test_speech.py` verify:
  - English, Bengali, and Hindi mock transcription with deterministic fixture matching and canonical fallback.
  - Ephemeral audio lifecycle: temporary files deleted in `finally` blocks on success, provider failure, and validation rejection.
  - Zero raw audio persistence in database or storage.
  - Strict consent enforcement: HTTP 403 `VOICE_CONSENT_REQUIRED` when `voice_processing = false`.
  - Non-editable session rejection: HTTP 409 `SESSION_LOCKED` when session is already completed.
  - File upload limits: HTTP 413 `FILE_TOO_LARGE` (>5MB), HTTP 422 `EMPTY_AUDIO` (0 bytes), HTTP 415 `UNSUPPORTED_MEDIA_TYPE`.
  - Candidate transcript isolation: ASR transcription does NOT create or mutate interview answers.
  - Provenance integrity: confirmed transcripts persist as `source: 'voice'`; edited transcripts persist as `source: 'typed'`.
  - Downstream normalization sequencing: clinical normalization runs only downstream after explicit patient confirmation.
  - TTS synthesis from pinned flow: strictly localized question text extracted; patient history/answers excluded.
- Total **47 frontend component tests** pass in Vitest:
  - 11 new tests in `speech.test.tsx` verify QuestionAudioPlayer states and VoiceRecorder recording, review card, edit, retry, and fallback flows.
- Total **12 Playwright E2E tests** pass in Chromium:
  - 5 new tests in `speech.spec.ts` verify English voice journey, Bengali voice journey, transcript edit before confirmation, ASR failure fallback to typed, and TTS question playback.
- Real process restart verification: `scripts/verify-restart.ps1` passes 100% across real backend and PostgreSQL process restarts.



