# Testing Strategy — MediKiosk

## Current executable checks

From the root on the configured Windows machine:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-backend.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-backend.ps1 -Postgres
cd frontend
npm run lint
npm run format:check
npm test
npm run build
npm run test:e2e
cd ..
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-stabilization-restart.ps1
```

Start the app with `scripts/start-dev.ps1 -NormalizationProvider mock` before browser/restart tests. Install the isolated browser once with `npx playwright install chromium` in `frontend/`.

The backend helper defaults to isolated SQLite tables and uses the dedicated `medikiosk_test` PostgreSQL database with `-Postgres`. Each PostgreSQL test rolls back its data using savepoints. The PostgreSQL suite applies migrations first and refuses a target whose database name does not end in `_test`.

The browser tests create fictional records in the running local demo database. The restart checker stops/restarts only the recorded project services and local PostgreSQL, then verifies the last browser-test record is unchanged. Do not run it during another person's active demo.

Current evidence and pending gates are recorded in [stabilization-implementation-status.md](stabilization-implementation-status.md). Run browsers against explicit mock providers, sequentially. Mock adapter tests never establish live provider success.

Run `backend/.venv/Scripts/python.exe scripts/verify-stabilization-migrations.py` for isolated upgrades from prior phase revisions, downgrade/reupgrade, preserved original-column hashes and actual Alembic comparison. It creates unique schemas in the existing test database and never reuses a pre-existing schema. Older phase-specific helpers are historical evidence tools; use this current verifier for stabilization.

`verify-stabilization-restart.ps1 -ApplicationOnly` verifies new backend/frontend process IDs and unchanged Phase 1–3, alert and document API state plus original document file hash, against the still-running PostgreSQL process. The same script without that switch requires actual PostgreSQL stop/start and a changed database PID. Windows Application Control currently prevents that full check; application-only success must not be reported as database restart acceptance.

The remaining strategy includes both retained historical expectations and current checks. The implementation-status and phase reports govern current claims; production security is not implemented.

## 1. Philosophy

The prototype should be impressive because it is **reliable and explainable**, not because it has many untested AI features.

Test deterministic behavior heavily. Test AI/provider boundaries with fixtures/contracts.

## 2. Test layers

### Backend unit tests — pytest
Cover:
- schema validation;
- interview state transitions;
- consent requirements;
- red-flag rules;
- timeline ordering;
- discrepancy logic;
- summary-confirmation state;
- authorization checks;
- provider adapters with mocks.

### Sarvam AI Adapter Unit Tests (Mocked Boundaries)
Cover:
- `test_sarvam_speech.py`: 14 tests verifying Bengali, Hindi, and English ASR/TTS, 16-kHz mono PCM16 audio format enforcement, timeout/rate-limit error mapping, empty transcript rejection, signed candidate generation, and zero live credential exposure.
- `test_sarvam_translation.py`: 13 tests covering bn→en, hi→en, en→bn translation, same-language short circuiting, language identification, transliteration, timeout/error propagation, staff authentication on doctor routes, and raw source answer immutability.
- `test_sarvam_ocr.py`: 12 tests covering document digitization initiation, bounded polling within 14s limit (28 polls at 0.5s), timeout handling, job failure mapping, HTML table and Markdown table parsing for lab observations, compound liquid dosage parsing (e.g. 5mg/5ml), end-to-end prescription and lab report fact materialization, cross-reference linkage, and strictly nullable confidence scores.
- `e2e/document-flow.spec.ts`: Playwright browser test validating patient consent, interview completion, UI document upload, live Sarvam OCR extraction, unverified medication/lab fact display, and doctor workspace document viewer linkage.

### Backend API integration tests
Cover:
- create patient/session;
- consent;
- record answer;
- fetch doctor session;
- summary edit;
- summary confirm;
- alert acknowledgement;
- document metadata lifecycle when introduced.

### Frontend unit/component tests
Use:
- Vitest;
- React Testing Library.

Cover:
- form validation;
- navigation guards;
- localized labels;
- loading/error states;
- verification labels;
- doctor summary editor.

### End-to-end
Playwright covers intake, source edits, normalization, speech confirmation/fallback, triage event delivery, document review, security rejections, mobile layouts and retained resume. Clinical validation and hosted provider acceptance are separate and unestablished.

Critical flows:
1. basic patient intake → doctor sees answers;
2. red-flag demo;
3. document upload → extraction → timeline;
4. doctor edit/confirm.

## 3. Phase 1 acceptance tests

### Patient flow
- user can select English/Bengali/Hindi;
- identification creates/associates a session;

- consent cannot be skipped if doctor-sharing is required;
- interview answers persist;
- page refresh does not silently create duplicate sessions if session ID is retained appropriately;
- completion hides previous patient data when a fresh intake starts.

### Doctor flow
- doctor can list sessions;
- doctor can open a session;
- captured answers appear correctly;
- doctor can edit summary;
- confirm stores verifier and timestamp;
- confirmed state is visible.

### API
- invalid payload returns 4xx;
- missing resource returns 404;
- database failure does not produce false success;
- health route works.

## 4. Red-flag testing

Each safety rule requires at least:
- positive case;
- negative case;
- boundary case if thresholds exist;
- missing-data case;
- explanation/trigger-fact assertion.

Example structure:

```python
def test_chest_pain_rule_fires_when_required_facts_present():
    ...

def test_chest_pain_rule_does_not_fire_without_required_fact():
    ...
```

Do not unit-test “the LLM knows medicine” as a safety guarantee.

## 5. AI extraction tests

When LLM integration begins:
- freeze representative input fixtures;
- assert Pydantic-valid outputs;
- assert unknown values are not invented;
- assert prohibited diagnosis/treatment fields are absent;
- test malformed provider response;
- test timeout;
- test provider unavailable.

Avoid tests that depend on nondeterministic live API responses in the default suite.

## 6. OCR tests

Fixture classes:
- clean printed prescription;
- clean lab report;
- rotated image;
- low-contrast image;
- poor handwriting sample if fallback exists.

Assertions:
- original document is preserved;
- confidence exists;
- low confidence stays unverified;
- extraction failure is represented explicitly.

## 7. Security tests

At minimum:
- unauthenticated protected route rejected once auth is introduced;
- patient-role cannot access doctor-only actions;
- doctor cannot confirm nonexistent session;
- unsafe object path/file access blocked;
- disallowed upload types/size handled;
- secrets not returned by config endpoints.

## 8. Test data

Use fictional data only.

Never place real patient records, identifiable prescriptions, phone numbers, addresses, ABHA identifiers, or hospital credentials in repository fixtures.

## 9. CI quality gates

Target commands:

Backend:
```bash
ruff check .
pytest
```

Frontend:
```bash
npm run lint
npm run test -- --run
npm run build
```

Add type-check command if not already part of build.

## 10. Definition of tested

A feature is considered tested when:
- happy path is covered;
- important invalid/error path is covered;
- clinically sensitive state transitions are covered;
- provider failure behavior is covered when external services are involved.

## Phase 2 adaptive interview acceptance

The backend suite now includes schema validation, all seven answer types, all five complaint families and isolated AYUSH traversal, completion, unknown/optional behavior, deterministic evaluation, consent/provenance guards, correction history, deactivation/reactivation, delayed retries, stale revisions, pinned versions and stable answer ordering. Original Phase 1 backend tests are unchanged. The existing ten frontend regressions now mock the server-driven interview contract and retain their identity/consent/save/resume/review assertions; seventeen new component tests cover renderers and adaptive UI behavior.

From the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-backend.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-backend.ps1 -Postgres
```

From backend, verify migrations with the existing local app/test PostgreSQL databases running:

```powershell
.\.venv\Scripts\python.exe ..\scripts\verify-phase2-migrations.py
```

This creates two isolated schemas inside medikiosk_test, exercises empty and Phase 1 upgrades, checks model/schema agreement, removes only those temporary schemas, then verifies the local app upgrade preserves every row in all Phase 1 tables using hashes. It refuses to overwrite a pre-existing verification schema. No application data is cleared.

From frontend:

```powershell
npm test
npm run lint
npm run format:check
npm run build
npm run test:e2e
```

The five browser tests include adaptive branch entry/edit/removal/restoration, refresh/resume, doctor confirmation, a legacy Phase 1 regression, Bengali mobile identity/questions, and persisted adaptive resume. They create fictional records in the local app database and deliberately leave them available for inspection. Screenshots and reference JSON files are under ignored .runtime.

After browser tests, from the project root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-stabilization-restart.ps1
```

The checker stops/restarts the actual backend and PostgreSQL, requires new PIDs, and compares legacy/Phase 2 confirmed records plus the unfinished Bengali interview (flow, cursor, revision, history and answers). Finally run `npm run test:e2e -- e2e/restart.spec.ts` from frontend to verify browser resume after the real restart.

See [current results](implementation-status.md) and [Phase 2 report](phase2-implementation-status.md). Clinical validation and provider integration are not established by these software tests.

## Phase 3A acceptance

Current totals: **159 backend tests on each SQLite/PostgreSQL profile**, including all 76 Phase 1/2 regressions and 83 new normalization tests; **33 frontend tests**; **7 Chromium E2E tests**. The new tests cover all fixtures, deterministic output, raw whitespace/EN/BN/HI preservation, negation/context/no-diagnosis fallback, malformed output, confidence/certainty, timeout/unavailability/unsupported language, field/type bypass, savepoint failures, source edits, cached retries, deactivation/reactivation, structured snapshots and unverified doctor labels after confirmation.

From backend with local PostgreSQL running:

```powershell
.\.venv\Scripts\python.exe ..\scripts\verify-phase3a-migrations.py
```

This verifies empty, Phase 1 and Phase 2 upgrades in isolated test schemas, then the real app upgrade; all pre-existing rows are fingerprint-compared. Alembic must report no new upgrade operations. Existing tests/start commands above remain valid.

After the full E2E suite, scripts/verify-stabilization-restart.ps1 compares both confirmed and unfinished Phase 3A source/result/provenance snapshots across real backend and PostgreSQL process restarts. Run `npm run test:e2e -- e2e/restart.spec.ts` afterward for two browser resume checks. Artifacts are stored in ignored .runtime. See [Phase 3A report](phase3a-implementation-status.md) for the reviewed defects and final evidence.

## Phase 3B acceptance

Current totals: **214 backend tests on each SQLite/PostgreSQL profile** (159 Phase 1/2/3A regressions + 55 Phase 3B contract and adversarial tests); **36 frontend tests**; **7 Chromium E2E tests**.

New test coverage includes:
- **Configuration & Secrets**: Mock defaults without API key, explicit `nvidia` configuration, invalid model/URL rejection without key echo, `SecretStr` representation and serialization exclusion.
- **Request Minimization**: Verification that only `text`, `language`, and `canonical_field` are sent; context IDs (`session_id`, `patient_name`) and API keys are completely stripped.
- **Conservative Sampling**: Verification of `temperature=0`, `stream=False`, `max_tokens=768`, and `chat_template_kwargs={"enable_thinking": False}`.
- **Schema 1.1 Enforcement**: Verification of required polarity (`present`/`absent`), certainty (`certain`/`uncertain`), `confidence: null`, exact evidence substring, and rejection of prohibited diagnostic concepts.
- **Fault Tolerance**: Network failures, timeouts, HTTP 401/403/429/500, truncated outputs, malformed JSON, duplicate keys, and schema violations all cleanly fail into explicit `unavailable` results while raw patient answers remain safely persisted.
- **Transaction Isolation**: Verification that normalization failures never roll back or poison the committed patient answer.
- **Secret Audit**: Value-based audit across 156 files and logs confirms zero API key leakage.
- **Migration Continuity**: `scripts/verify-phase3b-migrations.py` confirms clean upgrades from empty, Phase 1, Phase 2, and Phase 3A, with all pre-existing application table rows and SHA-256 fingerprints unchanged.
- **Empirical Live Diagnostic**: `scripts/evaluate-nvidia-normalization.py` probes live connectivity to `https://integrate.api.nvidia.com/v1`, testing `google/gemma-4-31b-it` directly.

## Phase 4A acceptance

Current totals: **231 backend tests on each SQLite/PostgreSQL profile** (214 Phase 1/2/3A/3B regressions + 17 Phase 4A speech and TTS tests); **47 frontend component tests**; **12 Chromium E2E tests**.

New test coverage includes:
- **Backend Unit & Integration Tests (`backend/tests/test_speech.py`)**:
  - Valid mock transcription for English, Bengali, and Hindi with fixture-matching and canonical fallback.
  - Strict consent enforcement: HTTP 403 `VOICE_CONSENT_REQUIRED` when `voice_processing = false`.
  - Non-editable session rejection: HTTP 409 `SESSION_LOCKED` when session is already completed.
  - Validation rejections: HTTP 415 `UNSUPPORTED_MEDIA_TYPE` (e.g. `image/png`), HTTP 422 `EMPTY_AUDIO` (0 bytes), HTTP 413 `FILE_TOO_LARGE` (>5MB), HTTP 400 `LANGUAGE_MISMATCH`.
  - Provider failure handling: deterministic timeout/unavailability simulation returning structured failure response without crashing.
  - Ephemeral audio cleanup verification: confirms temporary files are deleted from disk on success, provider error, and validation rejection.
  - Persistence non-mutation: confirms ASR transcription does NOT create or mutate interview answers.
  - Provenance verification: confirmed voice transcript persists as `source: 'voice'`; edited transcript persists as `source: 'typed'`.
  - Normalization sequencing: confirms clinical normalization runs only downstream after explicit answer confirmation.
  - Question TTS synthesis: verifies exact localized question text extraction, language matching, exclusion of patient answers/histories, and invalid question ID rejection (HTTP 404).

- **Frontend Component Tests (`frontend/src/test/speech.test.tsx`)**:
  - QuestionAudioPlayer: idle state, playback start, audio loading/playing, and error retry state.
  - VoiceRecorder: browser MediaRecorder availability check, permission denied fallback banner, start/stop recording states, candidate transcript display card ("You said: ..."), confirm action, edit action with inline text saving, retry/record again action, and cancel action.
  - Multilingual localization: verified label rendering for English, Bengali, and Hindi.

- **Playwright E2E Tests (`frontend/e2e/speech.spec.ts`)**:
  - Mock `MediaRecorder` injected into browser context to enable deterministic headless testing without physical microphone hardware.
  - Test 1: English voice intake journey with candidate review, explicit confirmation, persistence as `source: 'voice'`, and subsequent clinical normalization.
  - Test 2: Bengali voice intake journey with Bengali candidate review ("আপনি বলেছেন: ..."), explicit confirmation, and persistence.
  - Test 3: Transcript edit before confirmation, verifying edited text is submitted with `source: 'typed'`.
  - Test 4: ASR failure leading to graceful fallback message and typed answer submission.
  - Test 5: Question TTS playback request via the `Listen` button in the question header.

- **Full Regression & Restart Verification**:
  - SQLite regression: 231 passed in 10.80s.
  - PostgreSQL regression: 231 passed in 14.67s.
  - Full frontend suite: 47 tests passed in 1.45s.
  - Full E2E suite: 12 tests across 5 spec files passed in 44.6s.
  - Real service restart verification: `scripts/verify-stabilization-restart.ps1` passed 100% across real backend and PostgreSQL processes.

## Phase 7 acceptance

Current verified totals are **364 backend tests on SQLite**, **98 frontend component tests**, and **29 Chromium E2E tests** against the migrated local SQLite acceptance database. The suite includes browser recording conversion/TTS fallback coverage, Sarvam SDK contract/error/audio-boundary coverage, and a real fixture upload-to-extraction/timeline/preview journey. The PostgreSQL profile is not currently verified because the Windows PostgreSQL service is disabled and stopped.

`backend/tests/test_phase7_repairs.py` retains materialization, idempotence, atomicity, schema-alignment, provenance, null, and logging regressions. `backend/tests/test_phase7_complete.py` adds staff authorization, source exclusion, stable retrieval, verify/reject/correct review, forged identity, optimistic conflict, original/revision preservation, confirmed-state lock, timeline ordering/unknown dates/determinism/no duplicates, and conservative medication/allergy/lab discrepancy coverage.

`frontend/src/test/phase7.test.tsx` covers known/unknown timeline rendering, source badges, review correction, discrepancy/no-discrepancy, loading/error/unauthorized behavior, and mobile structure. `frontend/e2e/phase7.spec.ts` exercises four real-browser synthetic journeys: prescription facts/source trace/timeline, lab null/mobile display, patient-document possible discrepancy, and correction/verification/rejection with original source retained.

Run the standard full commands at the top of this document. `scripts/verify-stabilization-migrations.py` now verifies the Phase 7 additive migration and current Alembic/model comparison. Full PostgreSQL process restart remains blocked by Windows Application Control; `-ApplicationOnly` is not database-restart acceptance.

## Phase 8 acceptance

Current totals are **335 backend tests** on each SQLite/PostgreSQL profile, **67 frontend component tests**, and all existing E2E regression journeys.

1. **Backend Integration & Unit Tests (`backend/tests/test_phase8_summary.py`)**:
   - `test_clinical_summary_service_deterministic_10_sections`: Verifies deterministic synthesis of all 10 required clinical summary sections from structured sources (raw answers, medical facts, timeline, discrepancies, and safety screening alerts) without LLM invocation. Confirms zero diagnostic claims or prescription assertions.
   - `test_clinical_summary_ayush_banner`: Confirms prominent AYUSH demonstration disclaimers and supportive-documentation notices when AYUSH flows or answers are detected.
   - `test_doctor_summary_api_workflow`: Validates full clinician workflow: GET summary with evidence mappings; PUT working draft review with optimistic locking and automatic revision logging; rejection of stale versions (HTTP 409 `VERSION_CONFLICT`); draft regeneration conflict handling (HTTP 409 `CONFIRM_REPLACEMENT_REQUIRED` when manual edits exist); successful regeneration with `confirm_replacement=True`; append-only revision history retrieval; evidence endpoint source attribution; final confirmation locking (`POST /confirm`); and permanent immutability enforcement preventing subsequent edits or regeneration (HTTP 409 `CONFIRMED_IMMUTABLE`).
   - `test_doctor_summary_security_unauthorized`: Verifies that unauthorized callers without staff credentials are rejected (HTTP 401).

2. **Database Migration Verification (`scripts/verify-phase8-migrations.py`)**:
   - Migration `1915850a59d1_phase8_draft_summary.py` tested for clean empty database upgrades, Phase 7 → Phase 8 upgrades, and downgrade/re-upgrade cycles.
   - Alembic comparison against active models reports zero schema drift.

3. **Frontend Component Tests (`frontend/src/test/phase8.test.tsx`)**:
   - `renders summary editor with draft content and metadata badges`: Verifies version tags, draft status, and disabled confirm button until reviewed.
   - `allows editing working draft, inputting revision notes, and saving`: Verifies clinician edits, optional revision notes, and save review API interaction.
   - `switches to evidence attribution view and displays source links`: Verifies statement-to-source traceability display for all evidence types.
   - `switches to revision history view and loads revisions from API`: Verifies display of chronological revision feed, actors (`DOCTOR` vs `SYSTEM`), and revision notes.
   - `handles draft regeneration and confirms replacement when manual edits exist`: Verifies 409 conflict handling and modal replacement confirmation.
   - `locks editor and displays confirmed banner in read-only confirmed state`: Verifies read-only textarea and omission of mutating actions upon confirmation.

## Phase 9 acceptance

Current totals are **340 backend tests** and **73 frontend component tests**.

1. **Backend Tests (`backend/tests/test_phase9_hardening.py`)**:
   - `test_field_verification_lifecycle`: Verifies creation, optimistic updates, conflict handling, revision history, and synchronization with `interview_answers.verification_status`.
   - `test_confirmed_summary_amendment`: Verifies confirmed record immutability (`confirmed_text` strictly preserved), versioned clinical addendum creation, mandatory notes validation (min 3 chars), and status transition to `"amended"`.
   - `test_audit_trail_endpoint`: Verifies retrieval of immutable chronological session events with actor classifications (`DOCTOR`, `PATIENT`, `SYSTEM`) and event metadata.
   - `test_cross_references_endpoint`: Verifies bidirectional mapping connecting source documents, extractions, structured medications, observations, discrepancies, and summary statements.
   - `test_phase9_security_and_forgery_rejection`: Verifies server-enforced identity provenance, rejection of forged client identity parameters, and unauthorized access rejection.

2. **Database Migration Verification (`scripts/verify-phase9-migrations.py`)**:
   - Migration `7a3e8b1c4f92_phase9_verification_hardening.py` tested for clean empty database upgrades, Phase 8 → Phase 9 upgrades, rollback/downgrades, and re-application across PostgreSQL and SQLite.
   - `alembic check` confirms zero schema drift against active ORM models.

3. **Frontend Component Tests (`frontend/src/test/phase9.test.tsx`)**:
   - `FieldVerificationBadge`: Validates unverified initial rendering, popover interaction, clinician note input, optimistic status updates to `verified` or `flagged`.
   - `SummaryAmendmentModal & SummaryWorkspace`: Validates modal launch from confirmed summaries, clinical justification requirement, amendment API interaction, and amendment card rendering.
   - `AuditTrailViewer`: Validates chronological audit event list rendering and client-side actor filtering (`All`, `Doctor`, `Patient`, `System`).
   - `DocumentViewer Cross-References`: Validates rendering of linked clinical facts and summary referenced indicator within the document preview card.



