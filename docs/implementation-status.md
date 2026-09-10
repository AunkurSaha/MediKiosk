# Implementation status — existing Phase 7 repairs (2026-09-10)

MediKiosk is a **synthetic-data local prototype**. The user authorized inspection and repair of already-written Phase 7 code. No missing roadmap features are being added. See [Phase 7 review](phase7-implementation-status.md) for the partial implementation and fixes. The [independent review](current-project-review-2026-09-09.md) is the authoritative original audit; the [stabilization report](stabilization-implementation-status.md) tracks remediation and acceptance.

Phase 1–3 architecture remains: pinned deterministic interviews, append-only source answers, optional provider-neutral normalization, and doctor-controlled summary confirmation. Phase 4–6 code exists, with remediation implemented for staff access, voice provenance, alert interpretation/delivery/reconciliation and document correctness. The remaining acceptance gate is recorded below.

Current verification: 320 backend tests on each SQLite and PostgreSQL profile, 55 frontend tests and 25 Playwright tests pass. Ruff, ESLint, Prettier, TypeScript/build, migration/data-preservation/Alembic checks and dependency/configured-secret audits pass. Application restart preserves seven API snapshots and the original document hash. Full PostgreSQL restart remains unverified; stabilization is not yet accepted as complete. A checkpoint from another work session exists, but it is not evidence that the restart gate passed.

The actual open-dashboard browser test now receives created, resolved and reactivated alert events. The document browser test renders lab rows, loads the authenticated original preview, attributes verification to the server doctor and rejects changes after summary confirmation. Browser regressions also reject missing/reused WebSocket admission tickets and display missing source lab flags as Not reported.

Windows Application Control currently blocks `pg_ctl.exe`. The existing PostgreSQL process remains available, but the required full database stop/restart verification is blocked pending the owner's Windows policy resolution. `start-dev.ps1 -UseRunningDatabase -NormalizationProvider mock` starts app services against that existing database without invoking cluster control.

NVIDIA adapter: offline tests pass; retained live evidence is 3/26 domain passes and 23 timeouts, plus a separate 0/5 smoke run. Reliable live acceptance remains open. BHASHINI: mocked adapter tests only; no demonstrated live ASR/TTS. Real OCR is not implemented. Mock OCR only recognizes content-addressed synthetic fixtures; arbitrary valid uploads are stored with extraction unavailable.

App: http://127.0.0.1:5175 · API: http://127.0.0.1:8010/docs · PostgreSQL: 127.0.0.1:55432 / medikiosk / public. Use backend/.venv. Credentials remain in ignored local files. Current schema head: c83f627f4053 (forward Phase 7 index repair above the already-applied merged scaffold). Medication/lab materialization is repaired; timeline and discrepancy workflows remain missing.

No production readiness, clinical validation, complete PII removal or live provider acceptance is claimed. Git already exists; the requested clean stabilization checkpoint must wait until the required remediation and verification are complete.
