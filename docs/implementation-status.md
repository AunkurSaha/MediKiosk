# Implementation status — Phase 7 complete (2026-09-10)

MediKiosk is a **synthetic-data local prototype**. Phase 7 is implemented through deterministic source-linked medication/lab facts, a computed timeline, conservative discrepancies, additive clinician review history, staff-only APIs, and doctor UI. See the [Phase 7 report](phase7-implementation-status.md). The [independent review](current-project-review-2026-09-09.md) and [stabilization report](stabilization-implementation-status.md) retain the earlier remediation record.

Phase 1–3 architecture remains: pinned deterministic interviews, append-only source answers, optional provider-neutral normalization, and doctor-controlled summary confirmation. Phase 4–6 code exists, with remediation implemented for staff access, voice provenance, alert interpretation/delivery/reconciliation and document correctness. The remaining acceptance gate is recorded below.

Current verification: 331 backend tests on each SQLite and PostgreSQL profile, 61 frontend tests and 27 Playwright tests pass. Ruff, ESLint, Prettier, TypeScript/build, migration/data-preservation/Alembic checks and dependency/configured-secret audits pass. Application-only restart/resume passes. Full PostgreSQL process restart remains unverified because Windows Application Control blocks `pg_ctl.exe`.

The actual open-dashboard browser test now receives created, resolved and reactivated alert events. The document browser test renders lab rows, loads the authenticated original preview, attributes verification to the server doctor and rejects changes after summary confirmation. Browser regressions also reject missing/reused WebSocket admission tickets and display missing source lab flags as Not reported.

Windows Application Control currently blocks `pg_ctl.exe`. The existing PostgreSQL process remains available, but the required full database stop/restart verification is blocked pending the owner's Windows policy resolution. `start-dev.ps1 -UseRunningDatabase -NormalizationProvider mock` starts app services against that existing database without invoking cluster control.

NVIDIA adapter: offline tests pass; retained live evidence is 3/26 domain passes and 23 timeouts, plus a separate 0/5 smoke run. Reliable live acceptance remains open. BHASHINI: mocked adapter tests only; no demonstrated live ASR/TTS. Real OCR is not implemented. Mock OCR only recognizes content-addressed synthetic fixtures; arbitrary valid uploads are stored with extraction unavailable.

App: http://127.0.0.1:5175 · API: http://127.0.0.1:8010/docs · PostgreSQL: 127.0.0.1:55432 / medikiosk / public. Use backend/.venv. Credentials remain in ignored local files. Current schema head: `d12f4a7b9c31`. Real OCR, Phase 8, FHIR, ABDM, production authentication, and production deployment remain out of scope.

No production readiness, clinical validation, complete PII removal, real OCR, or live provider acceptance is claimed. The full PostgreSQL process-restart limitation remains documented exactly; WDAC was not modified.
