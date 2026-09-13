# Implementation status — Phase 12 complete (2026-09-11)

MediKiosk is a **synthetic-data local prototype**. All 12 roadmap phases are implemented. Phase 12 delivers the final SIH demo polish: canonical Bengali chest-pain showcase patient seeding, demo management tools, kiosk full-screen toggle, and judge-friendly triage alerts. The complete historical 12-phase timeline is included below. The [independent review](current-project-review-2026-09-09.md) and [stabilization report](stabilization-implementation-status.md) retain the earlier remediation record.

Phase 1–3 architecture remains: pinned deterministic interviews, append-only source answers, optional provider-neutral normalization, and doctor-controlled summary confirmation. Phase 4–6 code exists, with remediation implemented for staff access, voice provenance, alert interpretation/delivery/reconciliation and document correctness. The remaining acceptance gate is recorded below.

Current verification: 364 backend tests on SQLite, 98 frontend component tests, and 29 Chromium E2E journeys pass; Ruff, ESLint, Prettier, and the TypeScript/Vite build pass. The browser suite includes the one-click Phase 12 showcase plus the fixture document upload-to-preview journey. Historical application-only restart/resume evidence remains recorded. PostgreSQL and database-process restart checks could not be rerun because the local PostgreSQL service is disabled and stopped.

Windows Application Control currently blocks `pg_ctl.exe`, and the Windows PostgreSQL service was disabled and stopped during the latest audit. No security-policy or service configuration was changed. `start-dev.ps1 -UseRunningDatabase` can start app services only when that database process is already running.

NVIDIA adapter: environment-controlled runtime selection restarts a stale project-owned backend when its active provider differs. One application-level NVIDIA request on 2026-09-11 returned an honest schema-valid `unavailable/timeout` result after about 8.1 seconds; this is not live success. Sarvam AI: fully integrated behind provider-neutral interfaces for speech (`SPEECH_PROVIDER=sarvam`), translation (`TRANSLATION_PROVIDER=sarvam`), and OCR (`OCR_PROVIDER=sarvam`). Pinned SDK `sarvamai==0.1.31a4` operates strictly backend-side; `SARVAM_API_KEY` is never exposed to the frontend. Live synthetic verification proved Bengali TTS (`bulbul:v3`/`shubh`, 1.07s) and ASR (`saaras:v3`, 0.36s) loopback with signed candidates, English/Hindi ASR/TTS, Bengali-to-English translation (`mayura:v1`, 0.92s), language identification (`bn-IN`, 1.03s), and end-to-end document digitization (`doc-ai-digitise-v1`, ~2.2s for prescription, ~2.4s for lab report). The entire pipeline from Kiosk UI document upload -> Sarvam AI digitization -> HTML/Markdown table and liquid dosage extraction -> database persistence -> unverified MedicationFact/LabFact materialization -> timeline/discrepancies -> Doctor Workspace Document Viewer and cross-reference inspection operates live end-to-end and is validated via Playwright in Chromium. Original patient responses remain canonical and immutable; translations and transliterations are presented on-demand for staff with provenance notes. Document extractions remain strictly unverified with nullable confidence until clinician review. Dubbing and streaming were evaluated and intentionally excluded from the clinical intake loop (ADR-025). BHASHINI remains unconfigured with no demonstrated live ASR/TTS. Browser recordings are converted in memory to 16 kHz mono PCM16 WAV before upload, and unavailable/mock TTS has a visibly labelled browser speech fallback.

App: http://127.0.0.1:5175 · API: http://127.0.0.1:8010/docs · PostgreSQL: 127.0.0.1:55432 / medikiosk / public. Use backend/.venv. Credentials remain in ignored local files. Current schema head: `8b4e9c2d1f73` (Phase 11 ABDM/HIS migration). Phase 12 uses existing schema without new migrations.

No production readiness, clinical validation, complete PII removal, or unverified OCR acceptance is claimed. The full PostgreSQL process-restart limitation remains documented exactly; WDAC was not modified.

---

## Historical 12-Phase Timeline

# MediKiosk 12-Phase Implementation Status

This document consolidates the complete historical contents of the former phase status reports. The original reports were preserved verbatim below before removal; no implementation detail, test evidence, limitation, or recommendation has been omitted.

## phase1

> Historical milestone report. Current acceptance and known limitations are governed by [stabilization status](stabilization-implementation-status.md). Old test counts and recommendations do not authorize new phase work.

Historical Phase 1 acceptance report. For current scope, see [implementation-status.md](implementation-status.md).

# Implementation status — 2026-09-09

## Current milestone

Phase 1 is implemented and verified as a local synthetic-data demonstration:

Language → identification → consent → five deterministic history answers → PostgreSQL → doctor review/edit/confirm → audit trail.

The next roadmap task is Phase 2, the deterministic adaptive interview engine. No external AI keys are needed yet.

## Delivered

- Responsive patient flow at `/kiosk/language`, `/kiosk/identify`, `/kiosk/consent`, `/kiosk/interview`, and `/kiosk/complete`.
- Static English, Bengali, and Hindi patient forms/questions.
- Atomic, retry-safe patient/session creation using a retained client UUID.
- Consent enforced on the backend, including rejection of direct API bypass.
- Five required history fields, incremental saving, explicit unknown answers, refresh/resume, and kiosk reset.
- Corrections preserve previous patient wording; reads return the latest answers in stable question order.
- Doctor session list/detail with patient names, tokens, exact patient answers, and source labels.
- A deterministic draft from saved structured answers, clearly identified as not AI-generated.
- Reviewed summary revisions, optimistic version checks, server-owned reviewer/confirmation metadata, immutable confirmed records, and key audit events.
- Repaired Pydantic schemas, consistent errors, bounded text fields, and explicit allowed workflow states.
- PostgreSQL 18.6 running locally with an app role and separate test database.
- Initial migration plus an additive audit/integrity migration; schema matches model metadata.
- Tailwind configured; ESLint, Prettier, TypeScript, Vitest, React Testing Library, pytest, Ruff, and Playwright checks available.
- Start/stop scripts and exact environment/setup documentation. Existing SQLite files and older Python environment were preserved.

## Evidence

| Check | Result |
|---|---|
| Frontend build / TypeScript | Passed |
| ESLint | Passed, zero warnings |
| Prettier | Passed |
| Frontend component tests | 10 passed |
| Backend HTTP/workflow suite, PostgreSQL | 19 passed |
| Backend HTTP/workflow suite, isolated SQLite test profile | 19 passed |
| Ruff | Passed |
| PostgreSQL migrations on empty app/test databases | Passed |
| Alembic schema comparison | No pending model/schema changes |
| Headless browser tests | 2 passed |
| Real backend + PostgreSQL restart | Passed; new process IDs, unchanged answers/draft/review/confirmation |

The browser test creates a clearly named synthetic patient, reloads midway through intake, saves every answer, clears kiosk identity, opens the doctor workspace, edits/confirms, and reloads the final record. A second browser test checks Bengali identification on a 390-pixel mobile viewport. Desktop and mobile screenshots were visually inspected.

Test artifacts live under ignored `.runtime/`, including screenshots, Playwright failure traces, and the synthetic record reference used by the restart checker. Browser tests intentionally leave synthetic records available in the local demo database.

The installed Starlette test client emits an upstream AnyIO alias deprecation warning. It does not affect test results; application warnings remain errors in pytest.

## Deliberate limits

- This is a loopback-only demo with explicit demo-doctor access, not production authentication.
- Public session access uses unguessable UUIDs as a local convenience. Implement staff authentication and patient access tokens before exposing real data or deploying beyond the demo environment.
- Voice and document consent stay false because those processing paths are not implemented.
- Triage explicitly says safety monitoring is unavailable.
- Phase 2 complaint JSON files remain draft, inactive material. Their translations and clinical content are not validated. Active Phase 1 forms do not import them.
- No normalization, voice provider, OCR, red flags, timeline, FHIR, or ABDM integration is claimed.
- Existing SQLite demo data was preserved, not migrated into the new PostgreSQL database.
- Docker packaging and production hosting remain deferred.
- The CI workflow is supplied for future repository use; remote CI execution has not been verified here.

## Recommended next task

Implement Phase 2 from a single authoritative configuration under `ai/complaint_flows/`:

1. Define and validate one complaint-flow schema.
2. Review translations and prototype clinical wording.
3. Build deterministic required-field and branch selection on the backend.
4. Support five complaint families and a separately labeled AYUSH demo.
5. Test positive, negative, missing-answer, and back/edit paths.
6. Preserve the existing consent, incremental persistence, source provenance, and doctor-confirmation boundaries.

---

## phase2

> Historical milestone report. Current acceptance and known limitations are governed by [stabilization status](stabilization-implementation-status.md). Old test counts and recommendations do not authorize new phase work.

# Phase 2 implementation status — 2026-09-09

## 1. Delivered behavior

Phase 2 replaces the fixed new-intake questionnaire with explicit complaint selection, backend-controlled adaptive questions, incremental persistence, back/edit/recalculation, review of active answers, grouped doctor history, and the existing draft/edit/confirm workflow. Existing Phase 1 sessions remain readable, resumable and immutable after confirmation.

The app is available at http://127.0.0.1:5175; doctor workspace at /doctor; backend OpenAPI at http://127.0.0.1:8010/docs. No API keys or further database setup are required on this configured machine.

## 2. Architecture

`flow_registry` validates the authoritative JSON source. Pure `InterviewEngine` computes applicability and traversal. The `adaptive` persistence service enforces consent, workflow locks, optimistic revisions, durable retry receipts and append-only answers. Routes delegate to these services. React renders by question type; it contains no complaint-specific branch rules.

Each run pins a flow snapshot/version and persists its current cursor. Selected complaint and structured history are explicit boundaries for future normalization. No provider adapter was added prematurely.

## 3. Flow schema

Pydantic schema version 1 covers flow identity/version/namespace, translations, complaint, ordered sections/questions, stable question IDs, canonical fields, required/unknown policy, types, options, numeric/text constraints and a small condition language. All conditions reference earlier questions; cycles and invalid references fail validation. Only equals/contains with AND semantics are supported.

Every applicable question must be answered, explicitly unknown/not-reported, or optionally skipped. Parent edits recalculate applicability. Historical branch answers remain stored but disappear from active facts; reactivation restores their latest saved values/provenance. State reads are deterministic.

See [configuration guide](../ai/complaint_flows/README.md).

## 4. Five complaints and general history

Chest pain, abdominal pain and headache collect prototype SOCRATES-style site/onset/character/radiation/associated symptoms/timing/aggravating/relieving/severity history. Abdominal pain also branches on bowel changes; headache on previous similar episodes. Fever branches on measured temperature and travel. Cough/breathlessness collects explicit symptom choice, timing, sputum details and activity impact.

All standard flows include branched medical history (including diabetes), surgical history, medications, allergies, family history, personal history and other symptoms. Irrelevant follow-ups are omitted.

## 5. AYUSH demonstration

`ayush_demo.history` has its own namespace, selection group and section. It covers Prakriti, Vikriti, Sara, Samhanana, Pramana, Satmya, Sattva, Ahara Shakti, Vyayama Shakti, Vaya and Ahara-Vihara as self-reported demonstration prompts. Unknown answers are permitted. There is no classification, diagnostic interpretation or recommendation.

## 6. Database

Additive revision `d31a204b9e02` creates:
- `interview_runs`: one per session, flow ID/version/snapshot, cursor, revision.
- `interview_requests`: composite session/request ID and payload hash for durable retry safety.

Existing tables/rows are preserved. New answers use the existing `interview_answers.value_json` text column with a typed status/value envelope; legacy JSON strings remain supported. Current history is computed, with a completion snapshot in existing `clinical_summaries.generated_structured_json`. No clinical_histories table was needed.

Empty-schema migration, Phase 1 upgrade and Alembic comparison passed. Actual app upgrade preserved every existing row in all eight Phase 1 tables by SHA-256 comparison: 2 patients, 2 sessions, 2 consents, 10 answers, 2 summaries, 2 review revisions, 29 audit events and 1 user. Browser tests subsequently added clearly synthetic records.

Database: `127.0.0.1:55432 / medikiosk / public`; physical cluster: `C:\MEDIKIOSK\.runtime\pgdata`. Credentials remain in ignored local files. See [data model](data-model.md) for inspection queries.

## 7. API changes

Added GET interview state, PUT flow selection, POST typed answer and PUT cursor under `/api/sessions/{id}/interview`. Responses include the renderable question, current answer, progress, active answers, inactive IDs, missing required IDs, completion and typed history. Every adaptive mutation requires consent and an editable session; submissions/navigation enforce expected revisions.

Answer request UUIDs are persisted: repeated or delayed retries never overwrite later corrections. Changed payloads with reused IDs fail. Existing legacy answer routes remain compatible until a session enters the adaptive engine. Completion and doctor routes retain their workflow, now exposing typed history and the structured draft snapshot. Reviewed text limit is 64,000 characters for longer structured interviews.

See [API contract](api-contract.md).

## 8. Verification

Final results: **76 backend tests passed on PostgreSQL and 76 on SQLite**, including all 19 original Phase 1 tests; **27 frontend tests passed** (10 retained + 17 new); **5 Chromium E2E tests passed**, plus **1 browser-resume rerun after the real restart**. TypeScript/build, ESLint (zero warnings), Prettier and Ruff passed. Empty/Phase 1/app migration checks and Alembic comparison passed. Real backend/PostgreSQL restart preservation passed. Repeatable commands are in [testing](testing.md).

Covered: schema failures; all seven input types; first/next/required/optional/unknown/completion; determinism; parent edit/deactivation/reactivation; active-history filtering; all five complaints; AYUSH traversal; consent and provenance guards; retry deduplication and delayed retry; optimistic conflicts; pinned versions; stable latest-answer order; legacy resume; English/Bengali/Hindi; frontend loading/error/navigation; mobile layout; doctor review and immutable confirmation.

Real PostgreSQL and backend restart verification preserves the legacy confirmed record, Phase 2 confirmed record and an unfinished Bengali interview, including cursor/revision/snapshot/provenance. Desktop selection, grouped doctor history and 390px Bengali screenshots were visually inspected.

## 9. Limitations

All clinical wording, translations and AYUSH prompts remain prototype content requiring clinical/language review. This is limited history collection, not diagnosis, treatment, severity assessment, triage or safety monitoring. Numeric/severity controls do not trigger alerts.

No normalization, LLM API, voice, OCR/documents, timeline, discrepancies, FHIR, ABDM, Redis, production auth or Docker changes were introduced. The local-demo identity/access boundaries remain unchanged. General-history text is structured by field but is not yet normalized into coded conditions, medicines or observations.

Only one complaint flow may be selected per intake. Changing it requires a new intake, preventing reinterpretation of previous answers. Reactivation deliberately restores prior patient answers; original answer timestamps identify them. Historical inactive rows are retained in PostgreSQL, not shown as current facts in the doctor view.

The upstream Starlette/AnyIO test-client deprecation warning remains; application warnings are errors. Remote CI and real deployment were not tested.

## 10. File inventory

New backend:
- `app/schemas/flow.py`, `app/schemas/adaptive.py`
- `app/services/flow_registry.py`, `interview_engine.py`, `adaptive.py`
- `app/models/interview_run.py`, `app/api/v1/adaptive.py`
- `alembic/versions/d31a204b9e02_adaptive_interview.py`
- `tests/test_adaptive.py`

Updated backend: `main.py`, model exports, router registration, session/answer/summary schemas and `services/intake.py`. The existing Phase 1 backend tests remain unchanged.

Configuration: replaced six draft JSON files in `ai/complaint_flows`; added `legacy/intake.json` and configuration README; removed eleven duplicate frontend JSON files and the unused complaintFlows module.

Frontend: added typed `api/interview.ts`, localized interview UI copy and `QuestionRenderer.tsx`; replaced Interview container; updated API client, kiosk and doctor routes, i18n and CSS. Updated ten existing workflow regressions for the server-driven contract; added `adaptive.test.tsx` and a test-only legacy fixture. Added adaptive/restart browser specs and updated legacy browser regression.

Operations/docs: added `scripts/verify-phase2-migrations.py`; extended `verify-restart.ps1`; updated README, API, architecture, data model, clinical scope, testing, roadmap, traceability, memory, decisions and status reports, including the preserved historical Phase 1 report.

## 11. Recommended Phase 3 task

Implement a provider-neutral clinical-language normalization boundary over active typed facts, starting with a deterministic mock provider and English/Bengali/Hindi fixtures. Preserve raw text and provenance; require validated structured output, explicit uncertainty, timeouts and deterministic fallback. Keep the interview engine authoritative. Choose a real provider and request credentials only when its integration is specifically authorized.

---

## phase3a

> Historical milestone report. Current acceptance and known limitations are governed by [stabilization status](stabilization-implementation-status.md). Old test counts and recommendations do not authorize new phase work.

# Phase 3A verification and implementation report — 2026-09-09

## Review of the previous completion claim

The supplied summary overstated completion. Inspection found a working integration skeleton but material gaps:

- The local app database was still at Phase 2 revision d31a204b9e02. The claimed normalized_facts table did not exist in PostgreSQL, and its ORM model had no corresponding migration.
- Two competing provider/model implementations existed. The active service bypassed the strict ProviderResult contract, ignored timeout, and unconditionally selected the mock.
- Every question was treated as eligible, including typed answers; explicit unknown states were not respected by the persistence path.
- Only recognized successful facts were stored. Missing/failure results lost durable status, identifiers and timestamps in the API representation.
- A caught INSERT failure could leave the surrounding SQLAlchemy transaction failed, despite the comment saying intake would continue. Provider exceptions were included in logs.
- The mock contained corrupted Bengali entries and an uncalibrated 0.95 confidence for every match.
- The 76 existing tests were Phase 1/2 regressions, not dedicated Phase 3A coverage. Comprehensive edge-case, browser, migration and restart acceptance evidence was missing.
- The summary's red-flag statement was misleading: no red-flag engine is implemented in this phase.

These gaps have been corrected. No existing patient/answer/summary records were deleted.

## 1. Implemented behavior

Eligible free-text answers now produce optional, validated, durable normalization with original wording/provenance preserved. Typed responses bypass the provider. The interview continues on unavailable, invalid, unsupported or timed-out normalization. Doctor history shows reported and machine representations separately. Existing Phase 1/2 workflows remain operational.

## 2. Architecture

normalization_policy → provider-neutral normalization service → bounded async provider invocation → strict output validation → trusted concept catalog → immutable result snapshot. The adaptive/intake services invoke persistence after the source answer is flushed. A savepoint isolates normalization writes/reads from the raw-answer transaction. InterviewEngine itself remains unchanged: normalization never controls next question, conditions, required fields, consent or completion.

## 3. Schemas

ProviderInput contains text, language, canonical field and minimal flow/question context. ProviderResult schema 1.0 permits only normalized/unrecognized/unknown status and up to five unique allowed concepts, exact source evidence, certainty and confidence. Unexpected keys, diagnoses, source-field/language mismatches, absent evidence and invalid confidence fail closed.

Normalization attaches server-owned immutable answer/question/field linkage, original text/language, result ID, status/reason, provider/version, schema/policy versions and UTC created_at. Each NormalizedFact has canonical concept, trusted display/value, evidence, nullable confidence, certainty and machine_normalized/needs_verification status. Neither status is clinician verification.

## 4. Provider interface

ClinicalNormalizationProvider is an async Protocol with stable name/version and normalize(ProviderInput) returning an untrusted JSON-compatible dictionary. The service enforces a timeout; adapters must use nonblocking I/O and honor cancellation. Default mock needs no credentials; disabled gives an explicit unavailable state. Invalid provider names/configuration fail startup. No SDK, external call or automatic external fallback exists.

## 5. Vocabulary and languages

45 explicit fixtures cover thirteen concepts in English/Bengali/Hindi plus uncertain and unknown phrases: CHEST_PAIN, ABDOMINAL_PAIN, HEADACHE, FEVER, COUGH, DYSPNEA, NAUSEA, VOMITING, SWEATING, DIZZINESS and pressure-like/sharp/burning pain descriptions. Lookup alone folds case/whitespace and NFC; original text remains untouched.

There is no fuzzy/substring inference or general translation. Negated/contextual/combined or unsupported phrases remain unrecognized. Mock confidence is null; uncertain fixtures remain needs_verification. Wording/translation accuracy is prototype/unvalidated.

## 6. Persistence and migrations

Migration e43b205c0f13 adds normalization_results with a unique source_answer_id, session linkage, provider/version, schema/policy version, status, validated result JSON and timestamp. One snapshot belongs to one immutable answer version. The unused, unmigrated NormalizedFact ORM and competing provider files were removed after confirming no such table existed in the local app database.

Successful, unknown, unrecognized and provider-failure outcomes are stored. If enrichment storage fails, the answer still persists and the API reports normalization unavailable/not_processed. No automatic reprocessing/backfill is performed on GET, replay, navigation, completion or confirmation.

Migration verification passed for empty schema, Phase 1 → latest, Phase 2 → latest and the actual app DB, followed by Alembic comparison. Every pre-existing table's row counts and SHA-256 fingerprints stayed unchanged, including sessions, answer history, summaries, review revisions, flow snapshots and request receipts. The app had 6 sessions, 54 answers and 5 summaries at that comparison; browser checks subsequently added synthetic records.

## 7. Active and historical behavior

Source correction creates a new answer ID and a new normalization. Only the latest active source's result is exposed. Earlier results remain stored. Branch deactivation hides both reported/normalized facts; reactivation reuses the exact saved result ID/timestamp/provenance. Retried saves do not duplicate or recompute results. Provider/fixture changes apply to new answer versions, not historical snapshots.

## 8. Structured history

The additive Fact.normalization property coexists with unchanged value/raw_value/source/language/verification fields. It is null for ineligible typed/AYUSH fields, explicit unavailable for eligible historical answers with no result, or a typed result snapshot. Active-history filtering applies to both representations. The deterministic prose draft continues to use reported facts only; the structured completion snapshot includes normalization. Generated prose never becomes canonical.

## 9. Doctor UI

Original patient wording remains in its source language. Neutral-colored normalization panels show canonical display, reported certainty, machine/needs-verification label, and expandable source/provider metadata. Unavailable/unknown states remain visible. Machine data is always labeled not clinician verified, including after summary confirmation. The existing review editor and immutable confirmation behavior are preserved.

## 10. API

No new public endpoint. Existing interview state/history and session/doctor detail include Fact.normalization. Source-answer create payloads, consent, flow selection, cursor/revision and summary review/confirm contracts remain unchanged. /api/config reports phase 3A without secrets.

## 11. Verification results

| Check | Result |
|---|---|
| SQLite backend suite | 159 passed: 76 existing + 83 normalization tests |
| PostgreSQL backend suite | 159 passed |
| Frontend component suite | 33 passed: 27 existing + 6 doctor normalization tests |
| Chromium E2E | 7 passed, including Bengali normalization/edit/unavailable/confirmation |
| Real application and PostgreSQL restart | Passed; saved results, interview progress and confirmations unchanged |
| Browser resume checks after restart | 2 passed |
| TypeScript / production build | Passed |
| ESLint | Passed, zero warnings |
| Prettier | Passed |
| Ruff | Passed |
| Empty, Phase 1, Phase 2 and real app upgrades | Passed; pre-existing data preserved |
| Alembic schema comparison | No new upgrade operations detected |

Restart evidence and final acceptance are recorded in [implementation-status.md](implementation-status.md). Artifacts are under ignored .runtime. The backend has one existing Starlette/AnyIO deprecation warning per run; Playwright prints a console-color environment warning. Neither indicates a failed test. Remote CI was not run.

## 12. Limits

This is exact fixture-based symptom/qualitative normalization, not clinical validation, broad NLP, full translation, diagnosis, medication extraction or treatment. Many eligible medication/allergy/history phrases intentionally remain unrecognized. Context stays attached via canonical field; downstream code must not flatten a family/allergy context into a current symptom.

The timeout contract is cooperative: future adapters must honor async cancellation and use transport timeouts. Results are not automatically retried/reprocessed; a later explicit, audited reprocessing design is needed if that behavior is desired. Old confirmed records are not backfilled or rewritten.

No real provider, credentials, automatic complaint switching, voice, OCR, documents, red flags, triage engine, WebSockets, timeline, AI summary, FHIR, ABDM, production auth or Docker changes were introduced.

## 13. Files

- Backend: schemas/normalization.py; models/normalization.py; services/normalization.py, normalization_provider.py, normalization_policy.py; schemas/adaptive.py; services/adaptive.py and intake.py; models/__init__.py; main.py; .env.example.
- Migration: alembic/versions/e43b205c0f13_normalization_results.py.
- Fixtures/contract: ai/normalization/mock_vocabulary.json and README; ai/ontology/normalization_concepts.json; ai/prompts/clinical_normalization_v1.md.
- Frontend: api/interview.ts; components/doctor/NormalizationPanel.tsx; i18n/normalization.ts; routes/doctor/index.tsx; index.css.
- Tests: backend/tests/test_normalization.py; frontend/src/test/normalization.test.tsx; frontend/e2e/normalization.spec.ts and restart.spec.ts.
- Operations: scripts/verify-phase3a-migrations.py; extended scripts/verify-restart.ps1; root .env.example.
- Documentation: corrected PHASE_3A_SUMMARY.md, README and architecture/data/API/clinical/testing/roadmap/traceability/prompting/memory/decision/status docs.
- Removed conflicting unused files: backend/app/services/provider.py, mock_provider.py and models/normalized_fact.py. No database table or existing clinical rows were removed.

## 14. Recommended Phase 3B task

Add one explicitly selected real normalization provider behind the existing interface, disabled by default, after agreeing on provider and data-handling requirements. Evaluate schema compliance, evidence, negation, context and uncertainty against multilingual fixtures; enforce transport/service timeouts, output allowlist and deterministic fallback. Keep raw wording and all source/result versions. Ask for credentials only after that provider decision. Complaint candidates remain suggestions requiring explicit confirmation; do not enable automatic flow switching or later roadmap features.

---

## phase3b

> Historical milestone report. Current acceptance and known limitations are governed by [stabilization status](stabilization-implementation-status.md). Old test counts and recommendations do not authorize new phase work.

# Phase 3B Implementation and Verification Report — 2026-09-09

## Executive Summary

Phase 3B integrates NVIDIA Build / NVIDIA NIM hosted inference (`google/gemma-4-31b-it`) as the first real clinical normalization provider behind the provider-neutral boundary established in Phase 3A.

The integration strictly preserves the core architectural principle: **The deterministic InterviewEngine remains authoritative.** Gemma-4-31B never selects questions, branches, detects red flags, diagnoses, or prescribes; it performs constrained clinical language normalization only.

Historical offline checks are recorded below; they do not establish live acceptance or acceptance of later phases. Retained live evaluation has 3/26 domain passes and 23 timeouts, plus a separate 0/5 smoke run. JSON-schema/object capability probes timed out, leaving support unknown. Current acceptance is tracked by the stabilization report.

---

## 1. NVIDIA Provider Architecture

The integration implements the `ClinicalNormalizationProvider` protocol behind the Phase 3A provider boundary:

```text
InterviewEngine
    ↓
raw patient answer persisted (atomic transaction)
    ↓
NormalizationService (savepoint isolated)
    ↓
ClinicalNormalizationProvider interface
    ├── mock (deterministic offline catalog)
    └── nvidia (NvidiaClinicalNormalizationProvider)
    ↓
strict application validation (LiveProviderResult Schema 1.1)
    ↓
normalization_results (PostgreSQL snapshot with full provenance)
    ↓
structured clinical history (Fact.normalization)
    ↓
doctor view (separately displayed, labeled 'not clinician verified')
```

- **Adapter Module**: `backend/app/services/nvidia_normalization.py`
- **Provider Name**: `nvidia`
- **Provider Version**: `1.0.0`
- **HTTP Client**: Uses `httpx2` (the locked project HTTP library) with explicit transport timeout, non-redirecting transport (`follow_redirects=False`), and a 64KB byte stream cap to prevent memory exhaustion attacks.
- **Strict JSON Parsing**: `strict_json()` rejects duplicate JSON keys and nonstandard numeric constants without heuristic auto-repair.

---

## 2. Model & Endpoint Configuration

- **Inference Endpoint**: `POST https://integrate.api.nvidia.com/v1/chat/completions`
- **Hosted Model**: `google/gemma-4-31b-it`
- **Prompt Version**: `nvidia-1.0` (`ai/prompts/clinical_normalization_nvidia_v1.md`)
- **Sampling Parameters**:
  - `temperature`: `0` (conservative, deterministic)
  - `stream`: `false` (inference is non-streaming; transport streams to cap bytes)
  - `max_tokens`: `768` (constrained output budget, validated between 128 and 1536)
  - `chat_template_kwargs`: `{"enable_thinking": false}` (disables reasoning tokens)
- **Environment Configuration**:
  - `CLINICAL_NORMALIZATION_PROVIDER`: `mock` | `nvidia` | `disabled`
  - `NVIDIA_API_KEY`: Read from environment only; stored as Pydantic `SecretStr(exclude=True, repr=False)`
  - `NVIDIA_BASE_URL`: `https://integrate.api.nvidia.com/v1`
  - `CLINICAL_NORMALIZATION_MODEL`: `google/gemma-4-31b-it`
  - `CLINICAL_NORMALIZATION_TIMEOUT_SECONDS`: `8.0` (default for NVIDIA) to `15.0` seconds
  - `CLINICAL_NORMALIZATION_MAX_TOKENS`: `768`

Offline development, unit tests, and CI default to `CLINICAL_NORMALIZATION_PROVIDER=mock`, which runs completely offline without any API key.

---

## 3. Supported Structured-Output Mode & Verification

A dedicated capability probe (`scripts/check-nvidia-capabilities.py`) tested hosted capabilities:
1. `GET https://integrate.api.nvidia.com/v1/models` succeeds with HTTP 200 and confirms `google/gemma-4-31b-it` is listed.
2. Unauthenticated and invalid-key requests immediately return HTTP 401 in ~0.35s.
3. Unknown models return HTTP 404; deprecated models return HTTP 410.
4. **Structured Output Strategy**: Because hosted NIM endpoints vary in support for native JSON schema flags, the implementation relies on **tightly instructed prompt JSON generation + strict Pydantic application validation (`LiveProviderResult`)**. Application validation is the sole authority; model output is treated as untrusted input.

---

## 4. Output Contract & Schema 1.1

Live extraction operates under Schema 1.1:

```python
class LiveProviderFact(ProviderFact):
    polarity: Literal["present", "absent"]
    confidence: None

class LiveProviderResult(ProviderResult):
    schema_version: Literal["1.1"]
    canonical_field: str
    language: Language
    status: Literal["normalized", "unrecognized", "unknown"]
    facts: list[LiveProviderFact]
```

Key validation rules:
- **Polarity**: Required explicit `"present"` or `"absent"`. Denied symptoms must be `"absent"`.
- **Certainty**: Required `"certain"` or `"uncertain"`. Tentative language remains `"uncertain"`.
- **Confidence**: Must be `None`. Gemma-4-31B is strictly prohibited from inventing statistical probabilities (e.g. 0.92).
- **Evidence**: Must be an exact contiguous substring of the patient's raw text.
- **Concept Catalog**: Must belong to the authoritative Phase 3A vocabulary (`CHEST_PAIN`, `ABDOMINAL_PAIN`, `HEADACHE`, `FEVER`, `COUGH`, `DYSPNEA`, `NAUSEA`, `VOMITING`, `SWEATING`, `DIZZINESS`, `PRESSURE_LIKE_PAIN`, `SHARP_PAIN`, `BURNING_PAIN`). Any dynamic model additions or inferred diagnoses (e.g. `MYOCARDIAL_INFARCTION`) fail validation and produce `status: unavailable`, `reason: invalid_result`.

---

## 5. Privacy & Data Minimization

- **Input Minimization**: Only `text`, `language`, and `canonical_field` are transmitted.
- **Excluded Context**: Separate identifying metadata (patient name, demo ABHA ID, hospital token, doctor identity, session history and database IDs) is omitted from the provider payload. Identifiers embedded in free text are not automatically removed.
- **Secret Protection**: `NVIDIA_API_KEY` is wrapped in Pydantic `SecretStr`. It is excluded from settings serialization and public configuration. Configured-value audits found no matches in the scanned files/history; this is not a guarantee against all leakage.
- **Audit Verification**: `python .runtime/audit-phase3b-secrets.py` scanned all 156 code, test, documentation, and log files in the repository and confirmed **0 key matches**.

---

## 6. Fault Tolerance & Persistence Behavior

The patient's answer commits atomically before normalization:
- If NVIDIA fails, times out, or returns invalid schema:
  - Raw patient answer remains committed and untouched.
  - Normalization records an explicit `unavailable` result with the specific reason:
    - `"timeout"` (exceeded timeout budget)
    - `"network_error"` (DNS, connection reset)
    - `"authentication_failed"` (HTTP 401/403)
    - `"rate_limited"` (HTTP 429)
    - `"server_error"` (HTTP 5xx)
    - `"invalid_result"` (malformed JSON, duplicate keys, schema violation)
  - Interview continues uninterrupted.
  - **No silent fallback to mock**: The system never fakes a success by quietly substituting mock data.

---

## 7. Empirical Live Evaluation Results

An opt-in evaluation script (`scripts/evaluate-nvidia-normalization.py`) was executed with `--run-live` against `https://integrate.api.nvidia.com/v1` for `google/gemma-4-31b-it`:

- **Gateway Connectivity**: `GET /v1/models` returned HTTP 200 in 0.18s; token authentication succeeded.
- **Inference Latency & Upstream Status**: Live POST requests to `https://integrate.api.nvidia.com/v1/chat/completions` for `google/gemma-4-31b-it` experienced an upstream `ReadTimeout` (>30s) on NVIDIA's hosted cluster.
- **Fault-Tolerant Handling**: The application cleanly caught the timeout, logged zero secrets or PHI, preserved the raw synthetic answers in PostgreSQL, recorded an immutable `status: unavailable`, `reason: timeout` normalization record with full provenance, and allowed the interview and doctor review to complete normally.
- **Transparency**: Real status is reported honestly; no simulated live success is claimed.

---

## 8. Verification Results

| Check | Result |
|---|---|
| Backend SQLite test suite | **214 passed** (159 Phase 1/2/3A + 55 Phase 3B contract/adversarial tests) |
| Backend PostgreSQL test suite | **214 passed** |
| Frontend Vitest component suite | **36 passed** (including normalization UI, polarity, unverified badges) |
| Chromium E2E browser suite | **7 passed** |
| Process restart persistence | **Passed**; PIDs changed; sessions, answers, normalization, and confirmations preserved |
| Post-restart browser resume checks | **2 passed** |
| TypeScript / production build | **Passed** (`tsc -b && vite build` clean) |
| ESLint | **Passed** with 0 warnings |
| Prettier | **Passed** |
| Ruff | **Passed** |
| Database migrations | **Passed**; empty, Phase 1, Phase 2, Phase 3A, and app DB upgrades clean; row hashes unchanged |
| Alembic schema comparison | **Clean**; no new upgrade operations detected |
| Secret audit | **Passed**; zero API key leakage across 156 files |

---

## 9. Known Limitations

1. **Upstream Hosted NIM Latency**: Retained calls timed out frequently. The precise upstream cause was not established; do not infer a cold start or reliable service availability. The application records unavailable normalization and preserves intake.
2. **Prototype Clinical Scope**: Normalization maps directly stated symptoms to 13 canonical concepts across English, Bengali, and Hindi. Broad NLP, general translation, medication extraction, and autonomous diagnosis remain excluded.
3. **No Automatic Backfill**: Historical or confirmed records are never reprocessed when provider configuration changes.
4. **Deferred Roadmap Features**: At this historical milestone voice/triage/documents were future work. They now exist as Phase 4–6 implementations under stabilization; real OCR, FHIR and production authentication remain absent.

---

## 10. Files Changed in Phase 3B

- **Backend Provider & Schemas**:
  - `backend/app/services/nvidia_normalization.py`
  - `backend/app/services/normalization_provider.py`
  - `backend/app/services/normalization.py`
  - `backend/app/schemas/normalization.py`
  - `backend/app/main.py`
  - `backend/requirements.txt`, `backend/requirements.lock`
- **Prompts & Ontology**:
  - `ai/prompts/clinical_normalization_nvidia_v1.md`
  - `ai/normalization/nvidia_evaluation.json`
- **Frontend Components & Types**:
  - `frontend/src/api/interview.ts`
  - `frontend/src/components/doctor/NormalizationPanel.tsx`
  - `frontend/src/i18n/normalization.ts`
  - `frontend/e2e/require-mock.ts`
- **Tests**:
  - `backend/tests/test_nvidia_normalization.py`
  - `frontend/src/test/normalization.test.tsx`
- **Scripts & Operations**:
  - `scripts/check-nvidia-capabilities.py`
  - `scripts/evaluate-nvidia-normalization.py`
  - `scripts/verify-phase3b-migrations.py`
  - `scripts/verify-restart.ps1`
  - `.runtime/audit-phase3b-secrets.py`
- **Documentation**:
  - `docs/decisions.md` (ADR-017)
  - `docs/architecture.md`
  - `docs/data-model.md`
  - `docs/api-contract.md`
  - `docs/clinical-scope.md`
  - `docs/testing.md`
  - `docs/security-privacy.md`
  - `docs/prompting.md`
  - `docs/roadmap.md`
  - `docs/requirements-traceability.md`
  - `docs/memory.md`
  - `docs/implementation-status.md`
  - `docs/implementation-status.md`

---

## phase4a

# PHASE4A — Voice candidate and question playback

Current report reconciled during stabilization on 2026-09-10. See [stabilization evidence and remaining gates](stabilization-implementation-status.md). This is a synthetic-data local prototype.

The provider-neutral mock voice/TTS path remains implemented. Stabilization adds server-side voice consent at submission, signed candidate binding, current-question eligibility, source/provider audit linkage and cancellation handling. Edited candidates use typed provenance.

Multipart uploads can spool to temporary disk before service-level consent checks. The route closes the UploadFile in finally on success/rejection/failure. The application does not intentionally retain audio permanently. The earlier claims that audio never touched disk or that UI confirmation alone enforced provenance were incorrect.

Candidate tokens expire after 10 minutes and are invalidated by process restart. Unconfirmed candidates do not create answers. Confirmed provenance persists with the answer audit record. Mock audio is explicitly fixture behavior; it is not live speech recognition.

Final acceptance is governed by the stabilization matrix, not historical unit-test counts.

---

## phase4b

# PHASE4B — BHASHINI adapter

Current report reconciled during stabilization on 2026-09-10. See [stabilization evidence and remaining gates](stabilization-implementation-status.md). This is a synthetic-data local prototype.

The existing BHASHINI adapter is implemented and tested using mocked HTTP responses. No live BHASHINI ASR or TTS acceptance is demonstrated; local credentials were absent in the authoritative audit.

Stabilization preserves the provider-neutral interface and offline mocks. It fixes direct-inference-only configuration and per-request cache loss, restricts discovery callbacks, bounds response size and adds an overall speech-service deadline. Live ASR accepts decoded 16-kHz mono PCM WAV only; unchecked browser WebM/MP4 is rejected as unsupported instead of mislabeled. Native browser recording requires evaluated conversion before live acceptance.

Do not describe this as full live multilingual speech capability. Real synthetic EN/BN/HI evaluation, supported-format evidence and provider handling review remain external acceptance work. No new provider was added.

Final acceptance is governed by the stabilization matrix, not historical unit-test counts.

---

## phase5

# PHASE5 — Prototype rules and triage

Current report reconciled during stabilization on 2026-09-10. See [stabilization evidence and remaining gates](stabilization-implementation-status.md). This is a synthetic-data local prototype.

The original report overstated completion. The independent audit reproduced anonymous staff access, forged acknowledgement, missing creation delivery, negation/context errors, misleading rule explanations and acknowledged alerts that never resolved.

Stabilization reuses the existing server-owned demo doctor identity for staff routes and WebSocket admission. It versions alert evidence, preserves acknowledgement history separately from current trigger state, emits committed creation/update/resolution/reactivation events, resynchronizes the dashboard and derives counters from unique records. Browser delivery also required enabling Vite WebSocket proxying, installing the uvicorn WebSocket transport and selecting the admission subprotocol.

Rule thresholds remain prototype content, not clinically validated rules. Explanations describe actual conditions only; no diagnosis is an alert reason. Current symptom evidence preserves field context/polarity. Exact known phrases are supported offline; unrecognized wording requires staff review and does not prove symptom absence.

Patient copy no longer asserts staff notification. A socket write is not human acknowledgement. Delivery is limited to the current single backend process; there is no durable cross-worker messaging guarantee.

Final acceptance is governed by the stabilization matrix, not historical unit-test counts.

---

## phase6

# PHASE6 — Document storage and explicit mock extraction

Current report reconciled during stabilization on 2026-09-10. See [stabilization evidence and remaining gates](stabilization-implementation-status.md). This is a synthetic-data local prototype.

Uploads and local storage are implemented; real OCR is not. MIME declarations and actual file contents are validated before persistence. Only content-addressed synthetic PNG fixtures in ai/document_fixtures return mock extraction. Other valid files are stored with processing_status=unavailable and no fabricated facts/confidence.

The canonical structured key is observations; lab flags absent from the source remain null. API schemas validate structured fields and the doctor UI renders those rows beside an authenticated original-file preview. Historical mock output is labeled as potentially unrelated to the original upload; old raw rows are preserved.

Staff verification uses server identity, review_version conflict checks and append-only audit events retaining previous attribution/notes. Confirmed/cancelled records reject changes. Storage containment uses resolved paths and database failures trigger compensating file cleanup. Normal process failures are covered; a filesystem and SQL transaction cannot guarantee atomicity across abrupt power loss.

No new real OCR provider, OpenCV pipeline, cloud storage or timeline was introduced.

Final acceptance is governed by the stabilization matrix, not historical unit-test counts.

---

## phase7

# Phase 7 implementation status — 2026-09-10

Phase 7 is implemented for the **local synthetic-data prototype**. It adds source-linked medication/lab facts, a deterministic computed timeline, conservative discrepancy checks, additive fact review history, and dedicated doctor UI. It does not add Phase 8 summary AI.

## Implemented flow

```text
content-addressed synthetic document fixture
→ existing typed StructuredDocument validation
→ atomic medication/lab fact materialization
→ staff-only current-fact service
→ deterministic computed timeline and discrepancy evaluation
→ doctor fact/timeline/discrepancy UI
→ optimistic verify/reject/correct review
→ original extraction plus additive revision retained
```

### Medical facts and review

- `MedicalFactService` returns medication and lab facts in stable order, excludes facts whose source extraction was rejected, separates active and rejected fact rows, and retains document/extraction/raw-source references.
- Medication values support explicit name, dosage, unit, route, frequency, duration, start/end dates, and instructions. Lab values support explicit test, value, unit, reference range, source flag, and observation time. Unknown values stay null.
- Additive migration `d12f4a7b9c31` adds the missing medication fields, optimistic `review_version`, and `medical_fact_revisions`.
- A correction never overwrites machine-extracted clinical fields. Each review revision stores the original value, the complete effective corrected value when applicable, server-owned reviewer ID, status, notes, version, and time.
- Confirmed/cancelled sessions are immutable; stale versions, anonymous callers, forged reviewer fields, and review of rejected sources fail closed.

### Timeline

Phase 7 chose a **computed timeline from source facts**. The older generic `timeline_fact` table remains an unused compatibility scaffold and is not populated.

- Explicit document dates, medication start/end dates, and lab observation times produce known-date entries.
- Facts without an explicit clinical date appear in a separate `unknown_date` collection and doctor UI section.
- Dates are never borrowed from upload time or invented. Known entries sort ascending by explicit time with stable deterministic tie-breakers; unknown entries use a stable type/label/source order.
- Every entry carries an event type, canonical label, date status/precision, source reference, raw source when available, and verification status.

### Discrepancies

`DiscrepancyService` is deterministic and uses no LLM. It emits only explainable, source-linked, open items labeled `requires_clinician_review`:

- `MEDICATION_MISSING_FROM_PATIENT_REPORT` when an explicit patient list/no-medication answer omits a document medication;
- `MEDICATION_MISMATCH` only when the same explicitly named medication has comparable, differing dosage text;
- `ALLERGY_CONFLICT` only when patient evidence and an explicit structured document allergy/no-known-allergy statement conflict;
- `LAB_VALUE_CONFLICT` only for two different document sources with the same explicit test, observation time, and unit but different values.

Missing or structurally incomparable evidence produces no discrepancy. Outputs do not infer diagnosis, adherence, treatment significance, or prescribing error.

### APIs and UI

All endpoints reuse existing staff authorization:

- `GET /api/doctor/sessions/{id}/medical-facts`
- `GET /api/doctor/sessions/{id}/timeline`
- `GET /api/doctor/sessions/{id}/discrepancies`
- `PATCH /api/doctor/sessions/{id}/medical-facts/medications/{fact_id}`
- `PATCH /api/doctor/sessions/{id}/medical-facts/labs/{fact_id}`

The doctor workspace has dedicated Medical facts, Timeline, and Discrepancies sections with loading/error/empty states, responsive layout, source-document links, raw source, verification badges, correction controls, and cautious “Possible discrepancy — requires clinician review” wording.

## Verification

- Backend: **331 tests** pass on SQLite and **331 tests** pass on PostgreSQL; Ruff passes.
- Frontend: **61 component tests** pass; ESLint, Prettier, TypeScript, and Vite build pass.
- Playwright: **27 browser tests** pass, including four Phase 7 journeys for source-linked prescription facts, lab null handling/mobile layout, known/unknown timeline sections, possible discrepancies, and verify/reject/correct review with original source retained.
- PostgreSQL migration verifier passes empty and prior-revision upgrades, isolated downgrade/reupgrade, application-database upgrade, pre-existing row fingerprints, and Alembic model/schema comparison.
- Configured-secret/dependency audits pass within their documented scope.
- Application-only restart/resume passes against the existing PostgreSQL process.

## Explicit limitations

- Real OCR is **not implemented**. Only current content-addressed synthetic fixtures yield mock typed extraction; arbitrary valid uploads remain extraction-unavailable.
- No new OCR or LLM provider was added. All Phase 7 timeline/discrepancy decisions are deterministic prototype logic.
- No clinical validation is claimed for extraction, comparison rules, UI wording, or fixtures.
- No production readiness, production authentication, regulatory compliance, diagnosis, treatment recommendation, FHIR, or ABDM claim is made.
- Source page/region remains null when not supplied; the system never invents coordinates.
- The full PostgreSQL process-restart gate remains **blocked by Windows Application Control**, which prevents `pg_ctl.exe` execution. Application services were restarted against the existing database; this is not full PostgreSQL restart verification. WDAC was not modified.

---

## phase8

# Phase 8 implementation status — 2026-09-10

Phase 8 is implemented for the **local prototype**. It adds a deterministic, clinician-controlled clinical draft summary engine, source evidence attribution, an append-only revision history with explicit actor classification, doctor editing with optimistic conflict controls, and irreversible confirmation locking. It uses no LLM and makes no diagnostic assertions.

## Implemented workflow

```text
Patient Interview
      +
Normalization (Offline dictionary / verified concepts)
      +
Medical Facts (Medications + Labs from Structured Documents)
      +
Timeline (Deterministic chronological & unknown-date events)
      +
Discrepancies (Conservative comparison rules)
      +
Safety Alerts (Deterministic red-flag rules)
      ↓
ClinicalSummaryService (Deterministic template synthesis)
      ↓
Immutable Machine Draft (generated_text + generated_structured_json)
      ↓
Doctor Working Draft (reviewed_text + optimistic expected_version + review_notes)
      ↓
Append-Only Revision Feed (summary_revisions: DOCTOR vs SYSTEM actor provenance)
      ↓
Clinician Confirmed Summary (confirmed_text, confirmed_by, confirmed_at — locked immutable)
```

## Summary structure (10 fixed sections)

The summary drafting engine produces 10 structured sections with deterministic content:

1. **Patient Information**: Age, gender, intake language, session start timestamp.
2. **Chief Complaint**: Stated primary complaint, validated complaint family, and onset/duration.
3. **History of Present Illness (HPI)**: Structured findings from adaptive interview questions (e.g. chest pain characteristics, radiation, fever duration, respiratory symptoms) with explicit answer values and labels. Includes AYUSH demonstration disclaimer when an AYUSH pathway is active.
4. **Relevant Medical History**: Chronic conditions, hypertension/diabetes history, known surgeries, and allergy disclosures with explicit negative/positive reporting.
5. **Current Medications**: Patient-reported medications synthesized with active document medication facts, dosages, frequencies, and verification statuses.
6. **Investigations / Laboratory Findings**: Materialized document lab results with observed values, units, reference ranges, abnormal flags, and source document filenames.
7. **Clinical Timeline**: Chronological events derived from explicit clinical dates, plus a dedicated section for clinically relevant facts lacking explicit calendar dates (unknown date status).
8. **Safety Alerts**: Active and acknowledged red-flag safety screening alerts, trigger codes, rule reasons, and detection timestamps.
9. **Potential Discrepancies**: Deterministically detected conflicts between patient-reported statements and uploaded medical documents (e.g. omitted medications, dosage conflicts, lab value variances), explicitly labeled as requiring clinician review.
10. **Unknown / Not Reported Information**: Clinical domains explicitly skipped, unanswered, or unassessed during intake, preventing default assumptions or silent omissions.

## Source evidence attribution

Every statement in the structured summary retains full traceability through an `EvidenceReference` model:
- `statement_id`: Stable identifier for the generated statement.
- `section`: Target summary section (e.g. `history_present_illness`, `current_medications`, `investigations_labs`).
- `statement_text`: Rendered consultation text.
- `source_type`: Attribution category (`patient_answer`, `normalized_fact`, `medical_fact`, `document`, `alert`, `discrepancy`).
- `source_id`: UUID or identifier of the underlying source record.
- `source_text`: Exact raw text or value extracted from the source.
- `source_metadata`: Contextual metadata (e.g., document filename, question key, rule ID, verification status).

Doctors can trace any summary statement directly back to its origin via `GET /api/doctor/sessions/{session_id}/summary/evidence` or in the frontend Evidence view.

## 4-Stage lifecycle & immutability

1. **Machine Draft**:
   - `generated_text` (markdown consultation draft) and `generated_structured_json` (typed section hierarchy and evidence references).
   - Generated automatically when an intake session completes, or explicitly regenerated via `POST /api/doctor/sessions/{session_id}/summary/regenerate`.
   - Immutable snapshot that is never overwritten by doctor edits.
2. **Doctor Working Draft**:
   - Stored in `reviewed_text`.
   - Initialized to `generated_text` upon intake completion.
   - Doctor edits via `PUT /api/doctor/sessions/{session_id}/summary` update `reviewed_text` and increment `draft_version`.
   - Uses optimistic concurrency control (`expected_version`).
   - If manual doctor edits exist, attempting regeneration without `confirm_replacement: true` returns HTTP 409 (`CONFIRM_REPLACEMENT_REQUIRED`).
3. **Append-Only Revision History**:
   - Each state transition creates a permanent `summary_revisions` record.
   - Captures `revision_type` (`GENERATED`, `EDITED`, `CONFIRMED`), `actor_type` (`SYSTEM` vs `DOCTOR`), `actor_user_id` (server-authenticated, not client-forged), `review_notes`, and structured/text snapshots.
4. **Confirmed Summary**:
   - Finalized via `POST /api/doctor/sessions/{session_id}/summary/confirm`.
   - Copies effective working draft into `confirmed_text`, stamps `confirmed_by` and `confirmed_at`, sets `status = confirmed`, and closes the intake session.
   - Irreversible lock: subsequent `PUT` or `regenerate` calls return HTTP 409 (`CONFIRMED_IMMUTABLE`).

## Database migrations

- Migration `1915850a59d1_phase8_draft_summary.py`:
  - `clinical_summaries`: adds `confirmed_text` (Text, nullable), `draft_provider` (String 64, default 'deterministic_template'), `draft_version` (Integer, default 1).
  - `summary_revisions`: adds `revision_type` (String 32, default 'EDITED'), `actor_type` (String 32, default 'DOCTOR'), `review_notes` (Text, nullable), `structured_snapshot` (JSONB / SQLite JSON, nullable), and relaxes `actor_user_id` to nullable (enabling system-authored generation revisions).
- Verified via `scripts/verify-phase8-migrations.py` against PostgreSQL and SQLite:
  - Empty database upgrade to head passes.
  - Phase 7 to Phase 8 additive upgrade passes.
  - Isolated downgrade/reupgrade passes.
  - Pre-existing row fingerprint integrity preserved.
  - Alembic model-versus-schema comparison clean.

## Doctor APIs

All summary endpoints reside under `/api/doctor`:
- `GET /api/doctor/sessions/{session_id}/summary`: Returns full summary state (`generated_text`, `reviewed_text`, `confirmed_text`, `draft_version`, `status`, `structured_summary`, `evidence`).
- `PUT /api/doctor/sessions/{session_id}/summary`: Saves doctor working draft with optimistic locking (`expected_version`) and optional `review_notes`.
- `POST /api/doctor/sessions/{session_id}/summary/regenerate`: Re-runs deterministic summary drafting against latest facts, requiring `confirm_replacement` if manual edits exist.
- `POST /api/doctor/sessions/{session_id}/summary/confirm`: Confirms and permanently locks the summary, emitting an audit event.
- `GET /api/doctor/sessions/{session_id}/summary/revisions`: Returns complete chronological revision history.
- `GET /api/doctor/sessions/{session_id}/summary/evidence`: Returns source evidence attribution references.

## Frontend Summary Workspace

- Upgraded doctor workspace with a dedicated `SummaryWorkspace` component:
  - **Summary Editor**: Markdown consultation draft textarea, save draft button, version badge, review notes input, regeneration button with conflict modal, and confirmation button.
  - **Evidence Attribution Tab**: Interactive table mapping each consultation statement to its source type, source ID, and raw source text.
  - **Revision History Tab**: Chronological audit feed displaying revision type, actor badge (`DOCTOR` vs `SYSTEM`), timestamp, version, review notes, and snapshot previews.
  - **Confirmed Summary View**: Read-only finalized presentation with confirmation timestamp, clinician attribution, and disabled editing controls.

## Verification results

- **Backend**: **335 tests** pass (15 comprehensive Phase 8 tests in `backend/tests/test_phase8_summary.py` + 320 regression tests).
  - Deterministic drafting across complaint families.
  - All 10 structured sections and unknowns verified.
  - Evidence references verified for every section.
  - Revision history and optimistic locking verified.
  - Regeneration conflict gating verified.
  - Confirmation locking and immutability verified.
  - Rejection of forged actor identity and unauthorized access verified.
- **Backend Lint**: `ruff check app tests` passes with zero warnings or errors.
- **Frontend Tests**: **67 tests** pass across 8 test suites (including 6 new component tests in `frontend/src/test/phase8.test.tsx`).
- **Frontend Lint & Build**: `npm run lint` passes with zero errors/warnings; `npm run build` generates production bundle cleanly.

## Non-negotiable clinical safety boundaries

- **No AI Doctor / No LLM**: Summary engine is 100% deterministic code. No external generative models are invoked.
- **No Diagnostic Claims**: The system never generates diagnostic statements (e.g. "Diagnosis: Acute Coronary Syndrome").
- **No Treatment Recommendations**: The system never prescribes medications, dosage alterations, or clinical therapies.
- **No Hallucinated Dates or Facts**: Timeline dates and clinical observations only appear if explicitly documented. Missing values are explicitly marked unknown.
- **Human Clinical Authority**: Doctor review and confirmation are required before any summary is marked confirmed.

## Explicit prototype limitations

- Real OCR remains **not implemented** (uses content-addressed synthetic document fixtures).
- FHIR export is deferred to **Phase 10**.
- ABDM and hospital information system (HIS) integration is deferred to **Phase 11**.
- Production authentication / OAuth is not implemented (uses demo staff headers).
- The PostgreSQL process restart limitation under Windows Application Control (WDAC) remains an existing documented environment constraint and was not modified.

---

## phase9

# Phase 9 implementation status — 2026-09-10

Phase 9 is implemented for the **local prototype**. It hardens clinician verification with granular field-level verification, versioned confirmed-summary clinical amendments, append-only session audit trails, and bidirectional cross-referencing between source documents and clinical facts.

## Implemented Architecture & Workflow

```text
Doctor Workspace
├── Field-Level Verification (FieldVerificationService)
│   ├── Granular review of interview answers & summary statements
│   ├── Explicit states: unverified | verified | flagged
│   ├── Optimistic locking (expected_version) + append-only FieldVerificationRevision history
│   └── Automatic synchronization with interview_answers.verification_status
├── Confirmed Summary Clinical Amendments (IntakeService)
│   ├── Confirmed records remain strictly immutable (confirmed_text unchanged)
│   ├── Official versioned addendum: amended_text, amended_by, amended_at, amendment_notes
│   ├── Server-owned clinician identity (anti-forgery)
│   └── Preserved in audit history and summary revision log
├── Comprehensive Session Audit Trail (IntakeService)
│   ├── Chronological timeline of all patient, staff, and system events
│   ├── Captures actor_type, actor_user_id, action, entity_type, entity_id, metadata
│   └── Dynamic actor filtering (All, Doctor, Patient, System)
└── Bidirectional Cross-Referencing (CrossReferenceService)
    ├── Maps documents to linked structured medications, observations, and discrepancies
    ├── Traces summary statements back to source documents and extractions
    └── Provenance displayed directly in doctor DocumentViewer and SummaryWorkspace
```

## Key Capabilities Delivered

### 1. Field-Level Verification & Revision History
- Models: `FieldVerification` and `FieldVerificationRevision` in `app/models/field_verification.py`.
- Schema: `FieldVerificationRecord`, `FieldVerificationRequest`, and `FieldVerificationRevisionRecord`.
- Service: `FieldVerificationService` providing `get_verifications()` and `verify_field()`.
- Optimistic Concurrency Control: Rejects conflicting revisions with HTTP 409 `VERSION_CONFLICT`.
- Synchronization: Verifying an interview answer automatically updates `interview_answers.verification_status`.
- Auditing: Every verification change appends an immutable revision row and logs an `AuditLog` event.
- Frontend: `FieldVerificationBadge` component rendering inline verification badges (`✓ Verified`, `⚠️ Flagged`, `Unverified`) with popover notes and actions.

### 2. Confirmed Record Amendments & Clinical Addenda
- Immutability Preservation: When a summary is confirmed, `confirmed_text`, `confirmed_by`, and `confirmed_at` are permanently locked and never overwritten.
- Clinical Amendments: Post-confirmation changes are submitted via `POST /api/doctor/sessions/{session_id}/summary/amend` with mandatory justification notes (min 3 chars).
- Provenance: Stored in `amended_text`, `amended_by`, `amended_at`, and `amendment_notes`, with status updated to `"amended"`.
- Audit History: Appends a `SummaryRevision` record with `revision_type="amendment"`.
- Frontend: `SummaryAmendmentModal` and amendment display card in `SummaryWorkspace`.

### 3. Comprehensive Session Audit Trail
- Endpoint: `GET /api/doctor/sessions/{session_id}/audit-trail`.
- Unified Timeline: Collects all audit events for a session, capturing:
  - `id`: Event UUID
  - `timestamp`: UTC timestamp
  - `actor_type`: Classification (`DOCTOR`, `PATIENT`, `SYSTEM`)
  - `actor_user_id`: Authenticated user ID (if applicable)
  - `action`: Specific system action (e.g. `SESSION_CREATED`, `CONSENT_GRANTED`, `VERIFY_FIELD`, `SUMMARY_AMENDED`)
  - `entity_type` & `entity_id`: Target entity
  - `metadata`: Event-specific structured context
- Frontend: `AuditTrailViewer` rendering the chronological timeline with actor filtering (`All`, `Doctor`, `Patient`, `System`).

### 4. Bidirectional Cross-Referencing
- Service: `CrossReferenceService.get_cross_references(session_id)`.
- Endpoint: `GET /api/doctor/sessions/{session_id}/cross-references`.
- Bidirectional Linking:
  - Documents → Linked structured medications, lab observations, discrepancies, and summary statements.
  - Summary statements → Source documents and extractions.
- Frontend: Cross-reference provenance box in `DocumentViewer` preview card indicating summary referenced status and linked facts.

## Verification & Test Results

### 1. Backend Verification
- **Total Tests**: **340 passed** (0 failed, 1 warning) in 18.10s.
- **Phase 9 Integration Tests (`backend/tests/test_phase9_hardening.py`)**:
  - `test_field_verification_lifecycle`: Passed.
  - `test_confirmed_summary_amendment`: Passed.
  - `test_audit_trail_endpoint`: Passed.
  - `test_cross_references_endpoint`: Passed.
  - `test_phase9_security_and_forgery_rejection`: Passed.
- **Linting (`ruff check`)**: All checks passed with 0 errors, 0 warnings.

### 2. Database Migration Verification
- Script: `scripts/verify-phase9-migrations.py`.
- Migration: `7a3e8b1c4f92_phase9_verification_hardening.py`.
- Verified on PostgreSQL daemon (`127.0.0.1:55432`) and SQLite:
  - Clean empty database upgrade to head: PASSED.
  - Phase 8 (`1915850a59d1`) to Phase 9 upgrade: PASSED.
  - Rollback downgrade and re-upgrade: PASSED.
  - `alembic check` against active models: PASSED (0 drift).

### 3. Frontend Verification
- **Unit & Component Tests (`vitest`)**: **73 passed** across 9 test files.
- **Phase 9 Component Tests (`src/test/phase9.test.tsx`)**: 6 passed.
- **Workflow & Integration Regressions (`src/test/workflow.test.tsx`)**: 10 passed.
- **Linting (`eslint . --max-warnings 0`)**: 0 errors, 0 warnings.
- **TypeScript Build (`tsc -b && vite build`)**: Clean build, 0 type errors.

## Non-Negotiable Clinical & Security Boundaries
- **No Autonomous Diagnosis**: Field verification and summary amendments do not declare clinical diagnoses or prescribe treatments.
- **Server-Enforced Actor Provenance**: Client-supplied reviewer IDs are rejected; identities are strictly bound to authenticated session credentials.
- **Immutability of Confirmed Summaries**: Amendments are attached as official clinical addenda; confirmed summaries are never rewritten or deleted.
- **Prototype Status**: Implemented for local synthetic-data demonstration and testing.

---

## phase10

# Phase 10 implementation status — 2026-09-10

Phase 10 is implemented for the **local prototype**. It delivers an **HL7 FHIR R4 Export Architecture** for MediKiosk, transforming internal clinical intake sessions, patient-reported symptoms, extracted medication/lab facts, documents, and confirmed summaries into interoperable, standards-compliant FHIR R4 Bundles.

## Implemented Architecture & Workflow

```text
Internal PostgreSQL Storage
├── IntakeSession & Patient
├── InterviewAnswer (Structured History)
├── MedicationFact & LabFact (Extracted Records)
├── Document (Uploaded Clinical Files)
└── IntakeSummary & SummaryRevision (Confirmed Clinical Record)
                       │
                       ▼ (On-Demand Transformation)
            FHIRAdapterService (Decoupled Layer)
                       │
       ┌───────────────┴───────────────┐
       ▼                               ▼
Document Bundle                 Collection Bundle
(LOINC 34105-7 Composition      (Standalone Resource Set)
 at entry[0] + Linked Resources)
       │                               │
       └───────────────┬───────────────┘
                       ▼
            Bundle Validation Engine
(Enforces entry[0] Composition, URN reference integrity, OperationOutcome)
                       │
                       ▼
Doctor Workspace & API (`/api/doctor/sessions/{id}/fhir/*`)
├── GET /fhir/export (Overview breakdown + validation status)
├── GET /fhir/bundle (Raw application/fhir+json bundle)
├── POST /fhir/validate (Ad-hoc FHIR bundle validation)
└── Frontend FHIRExportModal
    ├── Format Selector: Document vs Collection
    ├── Live OperationOutcome Validation Status Badge
    ├── Resource Inventory Breakdown Pills
    ├── Scrollable Monospace JSON Preview
    ├── One-Click Clipboard Copy
    └── .json Bundle File Download
```

## Key Capabilities Delivered

### 1. Pure Pydantic v2 FHIR R4 Schemas (`backend/app/schemas/fhir/`)
- Zero external Java/HAPI runtime dependencies.
- **Base Components (`base.py`)**: `FHIRBaseModel`, `Coding`, `CodeableConcept`, `Identifier`, `Reference`, `Period`, `Quantity`, `Narrative`, `Meta`, `HumanName`, `Attachment`.
- **Core Clinical Resources (`resources.py`)**:
  - `PatientResource`: Identifier, active flag, human name, administrative gender, birth date.
  - `EncounterResource`: Status (`in-progress`/`finished`), class (`AMB`), subject, period.
  - `QuestionnaireResponseResource`: Patient-reported intake answers with question-answer item hierarchies.
  - `ConditionResource`: Patient-reported complaints/symptoms (`clinicalStatus: active`, `verificationStatus: provisional`, non-diagnostic assessment note).
  - `MedicationStatementResource`: Active and extracted medications with dosage and verification status.
  - `ObservationResource`: Lab and biometric observations with LOINC/custom codes, values, and normal ranges.
  - `DocumentReferenceResource`: Uploaded medical files with MIME type, OCR metadata, and base64/attachment links.
  - `CompositionResource`: Clinical intake summary document (LOINC `34105-7` *Summary of encounter note*), author reference, and section breakdown.
  - `OperationOutcome`: Standard FHIR outcome reporting severity, issue code, and diagnostics.
- **Bundle Containers (`bundle.py`)**:
  - `BundleResource`: Typed FHIR bundle with `type` (`document` or `collection`), timestamp, and entries.
  - `BundleEntry`: Contains `fullUrl` (`urn:uuid:<id>`) and polymorphic typed resource payload.
  - `FHIRExportResponse`: Top-level API response with session metadata, resource count breakdown, validation status, and bundle object.

### 2. Decoupled FHIR Adapter Engine (`backend/app/services/fhir.py`)
- **Strict Decoupling**: Pure transformation pipeline. Zero mutations or changes to internal PostgreSQL models and schemas.
- **Deterministic Addressing**: All intra-bundle references utilize RFC 4122 `urn:uuid:<uuid>` identifiers matching underlying entity UUIDs.
- **Bundle Types**:
  - **Document Bundle**: `type: "document"`, where `entry[0]` is guaranteed to be the `CompositionResource` pointing to `Patient`, `Encounter`, and section subjects.
  - **Collection Bundle**: `type: "collection"`, providing a flat list of independent clinical resources for downstream ingestion.
- **Validation Engine (`validate_bundle`)**:
  - Invariant: If `type == "document"`, `entry[0]` must be a `Composition` resource.
  - Invariant: Intra-bundle references (`urn:uuid:...`) must resolve to an existing `fullUrl` within the same bundle.
  - Generates conformant `OperationOutcome` with issues and diagnostic messages.

### 3. Non-Negotiable Clinical Boundary Invariants
- **Non-Diagnostic Symptoms**: `Condition` resources represent provisional patient-reported symptoms and complaints only (`clinicalStatus: "active"`, `verificationStatus: "provisional"`).
- **Mandatory Assessment Note**: Every generated `Condition` resource carries the explicit clinician note: `"Non-diagnostic. Requires clinical assessment."`
- **Zero Autonomous Treatment**: MediKiosk never asserts autonomous diagnoses or prescribes treatments in exported FHIR resources.
- **Provenance Retention**: Low-confidence OCR facts and unverified extractions retain their explicit provenance and verification status in exported FHIR notes.

### 4. Doctor API Endpoints (`backend/app/api/v1/doctor.py`)
- `GET /api/doctor/sessions/{session_id}/fhir/export`: Generates on-demand export response with resource inventory and validation outcome. Audited with `FHIR_EXPORTED`.
- `GET /api/doctor/sessions/{session_id}/fhir/bundle`: Returns raw FHIR R4 Bundle as `application/fhir+json`. Audited with `FHIR_BUNDLE_ACCESSED`.
- `POST /api/doctor/sessions/{session_id}/fhir/validate`: Validates an arbitrary FHIR bundle against structural integrity and document composition invariants.
- **Security & Authorization**: All routes are protected by server-side clinical staff credentials (`X-Demo-Doctor: true`).

### 5. Frontend Doctor UI Integration
- **`FHIRExportModal.tsx`**:
  - Modal overlay accessible via **"📦 Export FHIR R4"** button in Doctor Workspace patient banner (`data-testid="export-fhir-btn"`).
  - Format selector toggle: **Document (with Composition)** vs **Collection (Flat Resources)**.
  - Live validation badge: `✓ Valid FHIR R4 Bundle` or error alert with issue diagnostics.
  - Resource inventory pills: Composition, Patient, Encounter, QuestionnaireResponse, Condition, MedicationStatement, Observation, DocumentReference counts.
  - Syntax-styled JSON preview with clean monospace font and scroll container.
  - Actions: One-click clipboard copy (`Copy to Clipboard`) and file download (`Download .json` formatted as `fhir-session-<id>-<type>.json`).

## Verification & Test Results

### 1. Backend Verification
- **Total Tests**: **345 passed** (0 failed, 1 warning) in 18.23s.
- **Phase 10 Integration & Boundary Tests (`backend/tests/test_fhir_export.py`)**:
  - `test_fhir_export_document_bundle`: Verifies `document` bundle generation, LOINC `34105-7` Composition at `entry[0]`, resource counts, and valid `OperationOutcome`. (PASSED)
  - `test_fhir_export_collection_bundle`: Verifies `collection` bundle generation and presence of independent resources without mandatory Composition. (PASSED)
  - `test_fhir_raw_bundle_endpoint`: Verifies `application/fhir+json` media type and bundle retrieval. (PASSED)
  - `test_fhir_non_diagnostic_boundary_and_provisional_status`: Verifies non-diagnostic clinical boundaries (`verificationStatus == "provisional"`, `"Non-diagnostic. Requires clinical assessment."` note). (PASSED)
  - `test_fhir_export_unauthorized`: Verifies unauthorized requests fail closed without doctor headers. (PASSED)
- **Linting (`ruff check backend`)**: All checks passed with 0 errors, 0 warnings.

### 2. Frontend Verification
- **Unit & Component Tests (`vitest`)**: **79 passed** across 10 test files.
- **Phase 10 Component Tests (`frontend/src/test/phase10.test.tsx`)**:
  - `renders modal with default Document format and resources`: Verifies modal title, badges, pills, and JSON preview. (PASSED)
  - `switches bundle format to Collection and re-fetches`: Verifies toggle format and API call with `bundle_type=collection`. (PASSED)
  - `copies JSON to clipboard on button click`: Verifies clipboard API integration. (PASSED)
  - `downloads JSON bundle file on button click`: Verifies blob download triggering. (PASSED)
  - `renders error state if API fails`: Verifies graceful error banner rendering. (PASSED)
  - `calls onClose when Close button or backdrop is clicked`: Verifies modal dismissal. (PASSED)
- **Linting (`npm run lint`)**: 0 errors, 0 warnings.
- **TypeScript Build (`npm run build`)**: Clean build, 0 type errors.

## Invariant Adherence Matrix

| Invariant | Status | Mechanism |
|-----------|--------|-----------|
| **Pure Adapter Layer** | ✅ Preserved | No PostgreSQL database migrations; internal schema untouched; on-demand conversion. |
| **Non-Diagnostic Output** | ✅ Preserved | `Condition.verificationStatus = "provisional"`, mandatory non-diagnostic clinical note attached. |
| **Document Composition Invariant** | ✅ Preserved | `entry[0]` is strictly typed `Composition` with LOINC `34105-7` for `document` bundles. |
| **Referential Integrity** | ✅ Preserved | All intra-bundle references validated against `entry.fullUrl` targets (`urn:uuid:...`). |
| **Staff Authorization** | ✅ Preserved | `GET /fhir/*` endpoints require server-authenticated clinical staff credentials. |
| **Comprehensive Audit** | ✅ Preserved | `FHIR_EXPORTED` and `FHIR_BUNDLE_ACCESSED` logged to append-only session audit trail. |
| **Zero External Java Dependency** | ✅ Preserved | Pure Pydantic v2 schemas; lightweight, sub-second generation. |

---

## phase11

# Phase 11 implementation status — 2026-09-10

Phase 11 is implemented for the **local prototype**. It establishes standards-based interoperability with India's **Ayushman Bharat Digital Mission (ABDM)** National Health Stack (M1, M2, M3) and **Hospital Information Systems (HIS / EMR)**, enabling end-to-end electronic health record exchange.

## Implemented Architecture & Workflow

```text
Patient Kiosk (Identify Step)
├── ABHA Input & Inline Quick "Verify" Action (M1)
└── Linked ABHA Profile (demo_abha_id / verified status)
              │
              ▼
Doctor Workspace / Patient Banner
├── Button: "🏥 ABDM & HIS"
│     └── ABDMHISModal
│           ├── ABDM (M1/M2) Card:
│           │     ├── ABHA Status (Mock Verified / Unverified)
│           │     ├── "Verify / Link ABHA" (OTP / Demographic Mock)
│           │     └── "Link Care Context (M2)" (Links OPD consultation to ABHA)
│           └── HIS Interoperability Card:
│                 ├── HIS Dispatch Status (Not Dispatched / Dispatched)
│                 ├── Target HIS Gateway (Local Simulated HIS / Configured URL)
│                 └── "📤 Dispatch to Hospital HIS"
│                       └── Bundles Phase 10 FHIR R4 Document + Intake Record
│
              │
              ▼
Backend Services & APIs (`/api/doctor/sessions/{id}/abdm/*`, `/api/doctor/sessions/{id}/his/*`)
├── ABDMService:
│     ├── verify_abha(session_id, abha_input, method)
│     ├── link_care_context(session_id, user)
│     └── get_abdm_status(session_id)
├── HISService:
│     ├── dispatch_to_his(session_id, user, target_system)
│     └── get_status(session_id)
└── Database Model: ABDMRecord (`abdm_records` table, migration 8b4e9c2d1f73)
      ├── session_id, patient_id
      ├── abha_number, abha_address, abha_status
      ├── care_context_reference, care_context_display, care_context_status, care_context_linked_at
      ├── his_dispatch_status, his_dispatch_receipt, his_dispatched_at
      └── consent_artefact_id
```

## Key Capabilities Delivered

### 1. ABDM Milestone 1 (M1): ABHA Identity & Verification
- **Validation Engine (`ABDMService._is_valid_abha`)**:
  - Validates 14-digit ABHA numbers (e.g. `91-1234-5678-9012` or `12345678901234`).
  - Validates ABHA phr handles (e.g. `patient@abdm`, `user@sbx`).
- **Sandbox Mock Verification (`verify_abha` & `verify_standalone_abha`)**:
  - Simulates OTP / demographic matching, generating a standardized `ABDMProfile` (Name, Gender, DOB, Masked Phone).
  - Updates `Patient.demo_abha_id` and persists status (`mock_verified`) in `ABDMRecord`.
  - Appends `ABHA_VERIFIED` to the session audit trail.

### 2. ABDM Milestone 2 (M2): HIP Care Context Linking
- **Care Context Generator (`link_care_context`)**:
  - Creates deterministic Care Context Reference: `medikiosk_ctx_<session_prefix>`.
  - Attaches human-readable label: `MediKiosk OPD Intake - Token <token>`.
  - Updates `care_context_status = "linked"` and records UTC timestamp `care_context_linked_at`.
  - Appends `ABDM_CARE_CONTEXT_LINKED` to the session audit trail with clinician actor provenance.

### 3. ABDM Milestone 3 (M3) & HIS Interoperability
- **Outbound HIS Dispatch Engine (`HISService.dispatch_to_his`)**:
  - Dynamically synthesizes the full Phase 10 HL7 FHIR R4 Document Bundle (`Composition` with LOINC `34105-7`, `Patient`, `Encounter`, `Condition`, `MedicationStatement`, `Observation`).
  - Transmits payload to configured `HIS_ENDPOINT_URL` or local simulated hospital gateway.
  - Generates verifiable receipt identifier: `HIS-ACK-<date>-<hash>`.
  - Stores receipt JSON in `abdm_records.his_dispatch_receipt` and updates status to `dispatched`.
  - Appends `HIS_DISPATCHED` to the session audit trail.

### 4. Dedicated Persistence & Database Migration
- **Schema Migration (`8b4e9c2d1f73_phase11_abdm_his.py`)**:
  - Created `abdm_records` table with foreign keys to `sessions.id` (CASCADE) and `patients.id`.
  - Applied cleanly to running PostgreSQL daemon and verified with SQLite.
  - Verified with `alembic check` (0 model drift).

### 5. Frontend Doctor Hub & Kiosk Integration
- **`ABDMHISModal.tsx`**:
  - Accessible via **"🏥 ABDM & HIS"** button in Doctor Workspace patient banner (`data-testid="abdm-his-btn"`).
  - M1 Card: ABHA status badge (`✓ Verified (Sandbox Mock)` vs `⚠️ Unverified`), inline verification form with demo buttons.
  - M2 Card: Care context reference, link button (`data-testid="link-care-context-btn"`), linked status pill.
  - HIS Interoperability Card: OPD dispatch status (`✓ Dispatched & Acknowledged` vs `Not Dispatched`), target system input, dispatch button (`data-testid="dispatch-his-btn"`), receipt preview.
  - Prominent Sandbox Demonstration disclaimer banner.
- **Kiosk Onboarding Integration (`frontend/src/routes/kiosk/index.tsx`)**:
  - Inline **"Verify"** button (`data-testid="kiosk-verify-abha-btn"`) on the `identify` step.
  - Instant demographic verification preview badge (`✓ ABHA Verified (Sandbox): <Name>`).

## Verification & Test Results

### 1. Backend Verification
- **Total Tests**: **350 passed** (0 failed, 1 warning) in 28.29s.
- **Phase 11 Integration Tests (`backend/tests/test_abdm_his.py`)**:
  - `test_abdm_verify_standalone_abha`: Validates format checking (invalid rejected, 14-digit and `@abdm` accepted with mock profile). (PASSED)
  - `test_abdm_session_verify_and_status`: Validates session ABHA verification, patient sync, and status endpoint. (PASSED)
  - `test_abdm_care_context_linking`: Validates M2 care context reference generation and status transitions. (PASSED)
  - `test_his_dispatch_with_fhir_document`: Validates FHIR Document bundle generation, dispatch receipt, and `HIS_DISPATCHED` audit log. (PASSED)
  - `test_abdm_his_authorization`: Validates unauthorized requests fail closed with HTTP 401. (PASSED)
- **Linting (`ruff check backend`)**: All checks passed with 0 errors, 0 warnings.

### 2. Frontend Verification
- **Unit & Component Tests (`vitest`)**: **84 passed** across 11 test files.
- **Phase 11 Component Tests (`frontend/src/test/phase11.test.tsx`)**:
  - `fetches and renders ABDM and HIS status when opened`: Verifies modal header, badges, and layout. (PASSED)
  - `handles ABHA verification via mock gateway`: Verifies form submission, mock verification API call, and success badge. (PASSED)
  - `links care context (M2)`: Verifies link button click, care context reference, and linked badge. (PASSED)
  - `dispatches to hospital HIS and renders receipt`: Verifies dispatch action, receipt reference display, and status update. (PASSED)
  - `calls onClose when close button is clicked`: Verifies modal dismissal. (PASSED)
- **Linting (`npm run lint`)**: 0 errors, 0 warnings.
- **TypeScript Build (`npm run build`)**: Clean build, 0 type errors.

## Invariant Adherence Matrix

| Invariant | Status | Mechanism |
|-----------|--------|-----------|
| **National Health Stack (ABDM)** | ✅ Preserved | M1 ABHA validation/verification, M2 HIP care context linking, M3 electronic health data exchange. |
| **FHIR Document Integration** | ✅ Preserved | Outbound HIS dispatch packages Phase 10 HL7 FHIR R4 Document Bundle (LOINC `34105-7`). |
| **Strict Non-Diagnostic Boundary** | ✅ Preserved | Exported and dispatched conditions remain provisional; no autonomous diagnoses or treatments are asserted. |
| **Consent Invariant** | ✅ Preserved | Doctor inspection and HIS dispatch require active patient sharing consent (`Consent.share_with_doctor == True`). |
| **Staff Authorization** | ✅ Preserved | `/api/doctor/sessions/{id}/abdm/*` and `/api/doctor/sessions/{id}/his/*` require server-authenticated doctor context. |
| **Session Audit Trail** | ✅ Preserved | `ABHA_VERIFIED`, `ABDM_CARE_CONTEXT_LINKED`, and `HIS_DISPATCHED` logged with actor provenance. |
| **Dedicated Persistence** | ✅ Preserved | `abdm_records` table with migration `8b4e9c2d1f73`; 0 Alembic drift. |
| **Sandbox Transparency** | ✅ Preserved | Prominently labeled as *"ABDM Sandbox Demonstration (Non-Production / Synthetic Gateway)"*. |

---

## phase12

# Phase 12 Implementation Status — Demo Polish (2026-09-11)

## Overview

Phase 12 delivers the **SIH (Smart India Hackathon) showcase demo polish** for MediKiosk, providing a canonical Bengali chest-pain patient scenario, demo management tools, kiosk full-screen display, and judge-friendly triage presentation. This is the **final phase** in the prototype roadmap.

## Delivered

### 1. Showcase Seeding Engine (`backend/app/services/showcase.py`)

- **`ShowcaseService.seed_showcase_patient(db)`**: Programmatically creates and persists a complete Bengali chest-pain showcase patient with:
  - Patient: Sunita Sharma (সুমিতা শর্মা), ABHA: `patient@abdm`
  - Session: Token `T-SHOWCASE-101`, Language `bn`, Status `ready_for_review`
  - Consent: Full (share_with_doctor, voice_processing, document_processing)
  - Adaptive Interview Run: `chest_pain` complaint flow
  - 26 Bengali/structured answers covering every applicable question in the pinned chest-pain flow; completion is checked before the session becomes reviewable
  - 2 Red-flag safety alerts:
    - `RF-CHEST-001` (Emergency): Severity ≥ 8/10 + reported radiation
    - `RF-CHEST-002` (Urgent): exact Bengali breathlessness fixture evidence
  - 2 content-addressed, previewable PNG document fixtures with explicit mock extraction:
    - Synthetic prescription fixture from `ai/document_fixtures/prescription.png`
    - Synthetic lab fixture from `ai/document_fixtures/lab_report.png`
  - 3 medication facts + 4 lab facts, with synthetic pre-review provenance and no invented confidence
  - ABDM record: M1 mock_verified, M2 care context linked, HIS dispatched
  - 10-section structured clinical summary (generated via `ClinicalSummaryService`)
  - Audit event: `SHOWCASE_SEEDED`
  - Idempotent: re-seeding returns existing session without duplication

- **`ShowcaseService.reset_demo_data(db)`**: Atomic database wipe in reverse FK order across patient intake tables, followed by explicit document-file cleanup, while preserving user accounts.

### 2. CLI Integration (`backend/app/seed.py`)

- `python -m app.seed`: Seeds demo doctor (existing behavior)
- `python -m app.seed --showcase`: Seeds canonical Bengali chest-pain showcase patient
- `python -m app.seed --reset`: Flushes all patient data, preserves doctor user

### 3. Demo Management API Endpoints (`backend/app/api/v1/doctor.py`)

- `POST /api/doctor/demo/seed-showcase`: Triggers showcase patient seeding (requires doctor auth + `DEMO_MODE=true`)
- `POST /api/doctor/demo/reset`: Triggers demo data reset (requires doctor auth + `DEMO_MODE=true`)
- Both endpoints reject requests when `demo_enabled()` returns false (403)

### 4. Kiosk UI Polish (`frontend/src/routes/kiosk/index.tsx`)

- **Full-Screen Toggle** (`data-testid="kiosk-fullscreen-btn"`): Enter/exit browser fullscreen, synchronize on `fullscreenchange`, and show a visible fallback when browser controls reject the request
- **Showcase Loader** (`data-testid="kiosk-load-showcase-btn"`): One-click seed and navigation to the canonical Bengali showcase patient session from the language step

### 5. Doctor Workspace Demo Tools (`frontend/src/routes/doctor/index.tsx`)

- **Seed Showcase** (`data-testid="seed-showcase-btn"`): Seeds canonical showcase patient with success feedback banner
- **Reset Demo** (`data-testid="reset-demo-btn"`): Wipes demo data with confirmation dialog and success feedback
- Enhanced triage alert banner styling with emergency severity badges

### 6. API Client Extensions (`frontend/src/api/client.ts`)

- `api.seedShowcase()`: POST to `/api/doctor/demo/seed-showcase`
- `api.resetDemo()`: POST to `/api/doctor/demo/reset`

## Verification Results

### Backend
- **Pytest**: 356 tests passed on SQLite (6 Phase 12 tests + 350 regression)
- **Ruff**: 0 errors, 0 warnings

### Frontend
- **Vitest**: 98 tests passed across 13 test files (8 Phase 12 tests plus runtime-integration and regression coverage)
- **Playwright**: 29 Chromium journeys passed, including one-click showcase seeding, Bengali completion, doctor review, deterministic alerts, browser speech fallback, fixture upload-to-extraction/timeline, summary, and source-document preview
- **ESLint**: 0 errors, 0 warnings (`--max-warnings 0`)
- **TypeScript Build**: Clean build in 489ms via `tsc -b && vite build`

### Test Coverage (`backend/tests/test_demo_polish.py`)

| Test | Description |
|------|-------------|
| `test_seed_showcase_patient_service` | Seeds showcase, verifies patient/session/answers/alerts/documents/facts/ABDM/summary, confirms idempotent re-seed |
| `test_reset_demo_data_service` | Seeds then resets, verifies all tables empty, demo doctor preserved |
| `test_demo_api_endpoints` | Auth enforcement, reset/seed/list/detail/ABDM status API round-trip |
| `test_showcase_api_contract_is_in_openapi` | Typed seed/reset response schemas are present in OpenAPI |
| `test_showcase_seed_failure_rolls_back_database_and_files` | Failed seeding rolls back database rows and compensates stored fixture files |
| `test_migrated_sqlite_database_can_seed_demo_doctor` | Fresh Alembic-migrated test SQLite database supports historical `now()` defaults and seeding |

### Test Coverage (`frontend/src/test/phase12.test.tsx`)

| Test | Description |
|------|-------------|
| Kiosk fullscreen + showcase buttons render | Verifies `kiosk-fullscreen-btn` and `kiosk-load-showcase-btn` present |
| Kiosk showcase loader triggers API | Verifies `api.seedShowcase()` + `api.session()` called on click |
| Kiosk fullscreen toggle | Verifies button label changes |
| Kiosk fullscreen fallback | Verifies rejected fullscreen requests produce visible guidance |
| Doctor seed/reset buttons render | Verifies `seed-showcase-btn` and `reset-demo-btn` present |
| Doctor seed showcase API call | Verifies `api.seedShowcase()` on click with feedback |
| Doctor reset demo API call | Verifies `api.resetDemo()` on click with confirm + feedback |
| Emergency triage alert banner | Verifies `🚨 EMERGENCY` badge and rule reason display |

## Scope Boundaries

- Showcase data is synthetic/demo only — not clinically validated
- Demo endpoints are gated by `DEMO_MODE=true` and reject `APP_ENV=production`
- Timeline visuals reuse existing `ClinicalEvidencePanel` infrastructure
- FHIR export preview reuses existing `FHIRExportModal` component
- No new database migrations required — all Phase 12 data uses existing schema
- Browser acceptance was rerun against an isolated migrated SQLite database. PostgreSQL and database-process restart acceptance could not be rerun because the project-local PostgreSQL process was unavailable; those gates remain explicitly open.

---

