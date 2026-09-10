# MediKiosk

MediKiosk is a local SIH prototype for pre-consultation intake. The patient supplies a structured history; a doctor reviews, edits, and confirms it. It does not diagnose or prescribe.

## Current working scope

Phase 1–3 intake, adaptive questioning, optional normalization, PostgreSQL persistence, doctor review and confirmation remain implemented. Phase 4–6 adds mock speech, a BHASHINI adapter, deterministic demo alerts/triage and document storage with explicit synthetic extraction fixtures. These later phases are undergoing audit remediation; advancement is frozen.

The draft is a deterministic rendering of saved answers. Back/edit preserves prior source answers; resume uses the pinned flow and cursor. Confirmed records are locked. Doctor review remains separate from machine output.

Real OCR is not implemented. BHASHINI live ASR/TTS is not demonstrated. NVIDIA live evidence is mixed and does not establish reliable acceptance. Rules, question wording and translations are prototype content without clinical validation. See the [stabilization report](docs/stabilization-implementation-status.md) for each original finding, fix, regression, evidence and limitation. No Phase 7 work is authorized.

## Run on this configured Windows machine

From PowerShell in the project root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-dev.ps1 -NormalizationProvider mock
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

Windows Application Control currently blocks this machine's PostgreSQL control executable. While the existing database is running, use `scripts/start-dev.ps1 -NormalizationProvider mock -UseRunningDatabase` to start only the application services. Full database restart acceptance remains pending resolution through Windows security policy.

Structured data is in PostgreSQL database `medikiosk`, schema `public`: `patients`, `sessions`, `consents`, interview/answer and normalization tables, `alerts`, `documents`, `document_extractions`, summaries and audit records. Uploaded file bytes are in the configured local upload directory; PostgreSQL stores their object keys, hashes and metadata. Database files are under ignored `.runtime/pgdata`; inspect records through SQL or a database client rather than editing those files.

See [setup](docs/setup.md) for fresh installation and manual commands, [testing](docs/testing.md) for acceptance checks, and [implementation status](docs/implementation-status.md) for results and next work.

## Development rules

Read [CLAUDE.md](CLAUDE.md), the [decision log](docs/decisions.md), and the [roadmap](docs/roadmap.md) before making changes. Structured data remains canonical. Consent and verification are controlled by the backend. Unknown information must remain unknown. Preserve source wording and the doctor's review history.
