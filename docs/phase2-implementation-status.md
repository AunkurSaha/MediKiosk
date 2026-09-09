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
