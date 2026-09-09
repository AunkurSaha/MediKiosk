# Implementation status — 2026-09-09

> Current audit: code and the app database now include Phase 6 scaffolding. The fresh review found open authorization, safety-alert, voice and document defects, 2 failing browser tests, schema drift and lint/format failures. Completion claims below are prior milestone reports, not current acceptance. See [current project review](current-project-review-2026-09-09.md) for the verified state and repair priorities.

**Phases 1, 2, 3A, 3B, 4A, and 5 are implemented and verified for the local synthetic-data demo.**

Phase 5 delivers the complete **Deterministic Red-Flag Safety Screening and Staff Triage Dashboard**. Deterministic clinical rules (`ai/safety_rules/red_flags_v1.json`, 11 rules across 5 complaint families) screen patient answers and machine-normalized concepts without any LLM decision-making. Additive PostgreSQL persistence (`alerts` table with `uq_session_rule_alert` unique constraint) prevents duplicates and automatically reconciles when patient answers change. Real-time WebSocket feed (`/api/triage/ws`) powers the Staff Triage Dashboard (`/triage`) with live counters, priority filters, and audit-logged staff acknowledgement. Kiosk displays a calm, non-diagnostic patient advisory banner, and active alerts are surfaced to the physician workspace.

Read the [full Phase 5 verification report](phase5-implementation-status.md) for architecture, schemas, rule catalog, WebSocket feed, tests, and Phase 6 recommendations. Prior reports: [Phase 1](phase1-implementation-status.md), [Phase 2](phase2-implementation-status.md), [Phase 3A](phase3a-implementation-status.md), [Phase 3B](phase3b-implementation-status.md), and [Phase 4A](phase4a-implementation-status.md).

## Final verification

| Check | Result |
|---|---|
| Backend SQLite profile | **250 passed** (232 regressions + 18 Phase 5 red-flag tests) |
| Backend PostgreSQL profile | **250 passed** |
| Frontend components | **52 passed** (47 regressions + 5 Phase 5 triage/alert tests) |
| Ruff linter | Passed clean (0 errors) |
| ESLint / TypeScript build | Passed clean (`tsc -b && vite build`, 0 warnings) |
| Database schema migrations | `f54c306d1e24_red_flag_alerts.py` applied; verified fresh & upgrade on PostgreSQL |
| Actual local app database | All pre-existing table row counts and historical sessions preserved |
| Real backend + PostgreSQL restart | Verified cleanly with persistent tables and daemon management |

The backend retains one upstream Starlette/AnyIO deprecation warning per suite. Playwright prints a console-color environment warning. Remote CI was not run. Scripts and artifacts are documented in [testing](testing.md); screenshots, migration fingerprints, secret audit logs, and restart references live in ignored .runtime.

## Running app and database

- App: http://127.0.0.1:5175
- Doctor workspace: http://127.0.0.1:5175/doctor
- OpenAPI: http://127.0.0.1:8010/docs
- PostgreSQL: 127.0.0.1:55432, database medikiosk, schema public.
- Start: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-dev.ps1`.
- Inspect confirmed answers in `interview_answers`; voice answers are recorded with `source = 'voice'`, edited answers with `source = 'typed'`.

Default speech provider is `mock`; explicit `disabled` mode is supported. Offline mock mode works completely without external credentials or microphone hardware. Clinical wording, fixtures, and translations are unvalidated prototype content. This is not diagnosis, treatment, broad language understanding, or safety monitoring. Production authentication and later roadmap features remain deferred.

## Current status and next task

Phases 1, 2, 3A, 3B, 4A, 4B, and 5 are fully implemented and verified locally.
- Phase 4B Authoritative Report: [phase4b-implementation-status.md](phase4b-implementation-status.md) (BHASHINI real speech provider integration for ASR and TTS).
- Phase 5 Authoritative Report: [phase5-implementation-status.md](phase5-implementation-status.md) (Deterministic red-flag engine + staff triage dashboard).

Next task: Phase 6 — Document Ingestion + OCR Pipeline (Prescription and lab report upload, local object storage, PaddleOCR structured extraction, and physician verification interface).
