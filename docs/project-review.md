# MediKiosk project review — 2026-09-09

> Historical pre-repair assessment. The Phase 1 issues below have since been addressed.
> See [implementation-status.md](implementation-status.md) for current scope, verified checks, and remaining limits.

## Current position

Phase 1 (the deterministic patient-to-doctor foundation) is incomplete. Some Phase 2 complaint configuration and interview UI have been drafted, but the application does not yet demonstrate the Phase 1 end-to-end workflow.

This assessment is based on the local source, repository instructions, build/lint execution, and isolated backend probes. It is not an assessment of the other model's work history: this folder is not currently a Git repository, so commit history was unavailable.

The existing structure is reusable. A broad rewrite is unnecessary. Finish and verify the earliest incomplete phase before extending the AI features, as required by the roadmap and initial prompt.

## What exists

| Area | Evidence and status |
|---|---|
| Product and architecture | Extensive requirements, clinical boundaries, architecture decisions, and phased roadmap. Setup and status documents still largely describe the target state. |
| Frontend foundation | React/Vite/TypeScript app with kiosk, doctor, and triage routes. Build currently fails. |
| Patient interview | Complaint selection and question controls exist. Inputs are not wired to answer capture or backend persistence. |
| Backend foundation | FastAPI application, CRUD route modules, Pydantic schemas, SQLAlchemy models, and an initial Alembic migration exist. Application import succeeds in the existing environment. |
| Persistence | Six core entity models exist. Basic patient/session/answer creation works in isolated model-created SQLite tables. Local configuration uses SQLite; the accepted architecture specifies PostgreSQL. |
| Doctor workflow | Backend routes exist but review/detail/confirmation paths have defects. Frontend is a placeholder. |
| Adaptive configuration | Five complaint families and a separate AYUSH JSON file exist under `ai/complaint_flows/`. They are draft configuration, not a tested adaptive engine. |
| Multilingual support | English/Bengali/Hindi fields exist in configuration. Language selection is missing, and some translated text contains unrelated words and mixed scripts. |
| Later capabilities | No implemented LLM normalization, voice provider, red-flag engine, OCR pipeline, timeline, FHIR export, or ABDM connector was found. These are later roadmap phases. |

## Verification results

- `frontend`: `npm run build` fails with TypeScript errors, including a missing AYUSH JSON import, invalid type imports, incompatible question shapes, and an out-of-scope `prev` reference.
- `frontend`: `npm run lint` exits successfully with four warnings. It runs Oxlint, whereas the repository instructions specify ESLint/Prettier. Passing this command does not mean the app builds.
- Backend application import succeeds; Pydantic warns that `orm_mode` has been renamed to `from_attributes`.
- Backend probes used direct route functions and Pydantic response validation with synthetic data in an isolated in-memory SQLite database. They did not open or modify the existing database. They were not full HTTP/browser tests or PostgreSQL migration tests.
- Patient/session creation and answer persistence succeed in that isolated database.
- An answer is accepted without any consent record.
- Doctor identity is automatically supplied without credentials.
- Doctor detail response validation fails because required nested fields are missing, including patient `created_at` and answer `session_id`.
- Saving a new summary with the documented `reviewed_text`-only payload fails with `IntegrityError` because status has no default.
- Saving a summary with `status=reviewed`, and confirming a prepared summary, fail with `NameError`: `func` is not imported.
- The answer schema accepts client-supplied `clinician_verified` status. This must become a server-controlled clinical transition.
- The doctor list does not populate `patient_name`.
- No audit model/table exists in the SQLAlchemy metadata.
- The existing Python environment lacks pytest, Ruff, and HTTPX. Its installed Pydantic and SQLAlchemy versions differ from the dependency pins. Runtime imports also depend on JWT and email validation packages absent from `requirements.txt`.
- No frontend test script or Vitest/React Testing Library setup was found. `backend/test_api.py` is a print-based smoke script with incorrect API paths/methods and no assertions; it does not establish test coverage.

## Highest-priority gaps

1. **The frontend cannot build.** Fix `frontend/src/components/kiosk/complaintFlows.ts`, `types.ts`, and `Interview.tsx` coherently. Configuration is duplicated across three locations; the imported `frontend/src/assets/complaint_flows/ayush_demo.json` is missing even though copies exist elsewhere.
2. **The kiosk cannot produce a saved intake.** There are no frontend API calls, no language/identity/consent screens, and no answer-control bindings. Next/Finish advances without validating or saving answers, yet completion text claims responses were recorded.
3. **Doctor review is incomplete.** Implement the frontend list/detail/editor and repair backend response validation, summary defaults, timestamps, patient names, and confirmation state transitions.
4. **Workflow rules are unenforced.** Consent is not checked before recording answers. Arbitrary strings are accepted for important states; clients can submit verification metadata. Summary updates permit overwriting generated text and confirmation metadata. A version column alone does not preserve revision history.
5. **The actual setup diverges from the documented setup.** SQLite is configured locally, migration and runtime database defaults differ, routes use `/api/v1` instead of the documented contract, and the smoke script uses neither consistently. Tailwind utility classes are used without Tailwind installation/configuration. No ADR records these deviations.
6. **Evidence of completion is missing.** No meaningful automated suite, CI workflow, audit implementation, or reproducible fresh-install result was found. Existing migrations do not prove PostgreSQL startup or restart persistence.

## Recommended next milestone: complete Phase 1

Work in these bounded tasks, keeping the existing modular monolith:

1. **Restore a reproducible baseline.** Initialize local version control if this is the canonical working folder. Make dependency declarations match supported, tested runtime versions. Follow the accepted PostgreSQL decision, unify application/migration configuration, and verify migrations against an empty database. Resolve the API contract and implement the documented error envelope. Configure the required frontend styling and checks.
2. **Repair the backend workflow.** Validate patient/session existence and consent, restrict allowed states and answer sources, keep verification metadata server-owned, repair doctor response schemas, and make save/confirm reliable. Preserve draft and reviewed content separately, record verifier/time, and add key audit events. Use an explicitly configured and labeled demo doctor identity for local demonstration until real authentication is implemented.
3. **Complete the basic kiosk flow.** Build language → identification → consent → deterministic interview → completion. Start with the Phase 1 fields in `INITIAL_PROMPT.md`: chief complaint, onset/duration, medications, allergies, and relevant past history. Persist each answer before advancing; handle loading, failure, retry, refresh/resume, and clean session reset.
4. **Complete the doctor interface.** Show sessions with patient/token/status, display the exact saved answers and their source labels, and support summary editing and confirmation with visible persistence state.
5. **Add acceptance evidence as these tasks are implemented.** Use pytest for API/workflow tests and Vitest/React Testing Library for forms, consent, navigation, and review states. Test rejected consent bypass, invalid transitions, missing resources, save failures, confirmation metadata, and preserved drafts as well as the happy path.
6. **Reconcile documentation.** Update setup commands, API contract, roadmap status, and durable memory to match the implementation. Record genuine architecture changes in ADRs. Do not mark a feature done solely because a file or screen exists.

### Phase 1 acceptance gate

A repeatable synthetic-patient demonstration must prove:

1. A fresh setup starts successfully and migrations apply to PostgreSQL.
2. The patient selects a language, identifies themselves, and grants consent.
3. The system rejects clinical answer submission without required consent.
4. The patient enters answers and each successful save is acknowledged by the backend.
5. Refreshing the browser preserves the intended session without creating duplicates.
6. The doctor sees the same saved answers and can edit and confirm the summary.
7. Confirmation stores verifier/time, preserves the draft, and emits an audit event.
8. Answers and confirmation survive backend restart.
9. Starting a new intake clears the previous patient's browser state.
10. Build, type, lint, and meaningful automated tests pass.

## After Phase 1

Complete Phase 2 by consolidating complaint configurations into one authoritative source, validating their schemas, implementing deterministic required-field and branch logic, and testing the five complaint families plus a separately labeled AYUSH demonstration. Correct translations with competent language review before treating multilingual content as complete.

Then follow the existing roadmap: normalization adapters, voice, deterministic red flags/triage, document ingestion/OCR, timeline/discrepancies, AI summary, verification hardening, FHIR, and ABDM/demo integration. Keep later providers behind adapters and use clearly labeled mocks where integrations are unavailable.

## Suggested instruction for the implementation model

> Read CLAUDE.md, INITIAL_PROMPT.md, docs/decisions.md, docs/roadmap.md, and docs/project-review.md. Complete Phase 1 before extending Phase 2. Preserve the existing modular monolith and accepted stack. First restore reproducible frontend/backend startup and checks; then implement and test consent-gated patient intake through persisted doctor review and confirmation. Treat client-supplied verification metadata as untrusted, preserve draft content, and add audit events. Update setup, contracts, and phase status with actual passing evidence. Report any remaining acceptance failures explicitly.
