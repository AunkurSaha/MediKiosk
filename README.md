# MediKiosk

MediKiosk is a local SIH prototype for pre-consultation intake. The patient supplies a structured history; a doctor reviews, edits, and confirms it. It does not diagnose or prescribe.

## Current working scope

Through Phase 3A: English/Bengali/Hindi identification and consent → explicit complaint selection → deterministic adaptive questions → PostgreSQL persistence → grouped doctor history and review/confirmation → audit trail.

The draft is a deterministic rendering of active saved answers, not AI output. Back/edit recalculates branches while preserving prior answers; an interrupted interview resumes from its pinned flow and saved cursor. Confirmed records are read-only. The original draft and review revisions remain stored.

Five complaint families and a separate AYUSH demonstration are available. Question wording and translations are prototype content awaiting clinical review. A deterministic local mock now normalizes eligible free text using explicit English/Bengali/Hindi fixtures. The doctor sees original wording and machine concepts separately; failures leave intake working. Live AI providers, voice, OCR, red flags/triage, timelines, FHIR, and ABDM remain later phases. The triage page explicitly identifies its unavailable functionality.

## Run on this configured Windows machine

From PowerShell in the project root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-dev.ps1
```

- App: http://127.0.0.1:5175
- Doctor workspace: http://127.0.0.1:5175/doctor
- API docs: http://127.0.0.1:8010/docs
- Local PostgreSQL: 127.0.0.1:55432

The launcher starts hidden processes, applies migrations, and seeds a demo doctor. Ports 5175/8010 avoid pre-existing services on 5173/8000. Logs, PostgreSQL binaries/data, and generated credentials are in the ignored `.runtime/` directory. App credentials are in ignored `backend/.env`.

Use fictional patients only. Demo doctor access is explicitly enabled locally; production staff authentication and patient access tokens are not implemented. UUID-based session access is for this local demo, not an authorization scheme.

Stop the app, retaining the database:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/stop-dev.ps1
```

Stop the app and database, retaining all data:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/stop-dev.ps1 -Database
```

See the [Phase 3A verification report](docs/phase3a-implementation-status.md) for corrected gaps, exact test evidence and the next task.

See [setup](docs/setup.md) for fresh installation and manual commands, [testing](docs/testing.md) for acceptance checks, and [implementation status](docs/implementation-status.md) for results and next work.

## Development rules

Read [CLAUDE.md](CLAUDE.md), the [decision log](docs/decisions.md), and the [roadmap](docs/roadmap.md) before making changes. Structured data remains canonical. Consent and verification are controlled by the backend. Unknown information must remain unknown. Preserve source wording and the doctor's review history.
