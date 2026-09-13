# MediKiosk

MediKiosk is a local SIH prototype for pre-consultation intake. The patient supplies a structured history; a doctor reviews, edits, and confirms it. It does not diagnose or prescribe.

For a single end-to-end explanation of the roadmap, architecture, workflows, technology stack, and implementation, see the [complete project guide](docs/complete-project-guide.md).

## Current working scope

Phases 1–12 are implemented for the local synthetic-data prototype: deterministic intake, optional normalization, mock speech, deterministic safety alerts, document storage/typed fixture extraction, source-linked evidence and timeline, doctor-controlled summaries and amendments, FHIR R4 export, mock ABDM/HIS interoperability, and a seeded Bengali showcase journey.

The draft is a deterministic rendering of saved answers. Back/edit preserves prior source answers; resume uses the pinned flow and cursor. Confirmed records are locked. Doctor review remains separate from machine output.

Real OCR is not implemented. Sarvam REST ASR/TTS has a successful synthetic Bengali TTS-to-ASR loopback, but physical microphone and accent acceptance is not established. BHASHINI live ASR/TTS is not demonstrated. NVIDIA live evidence is mixed and does not establish reliable acceptance. Rules, question wording, translations, extraction fixtures, and discrepancy comparisons are prototype content without clinical validation. See the [current implementation status](docs/implementation-status.md), [Phase 12 report](docs/phase12-implementation-status.md), and [stabilization report](docs/stabilization-implementation-status.md) for evidence and limitations.

## Run on this configured Windows machine

From PowerShell in the project root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-dev.ps1
```

- App: http://127.0.0.1:5175
- Doctor workspace: http://127.0.0.1:5175/doctor
- API docs: http://127.0.0.1:8010/docs
- Local PostgreSQL: 127.0.0.1:55432

The launcher starts hidden processes, applies migrations, seeds a demo doctor, and uses the normalization provider selected in `backend/.env`. If a project-owned backend is already running with a different provider, the launcher restarts that backend so `/api/config` reflects the current selection. Use `-NormalizationProvider mock` only for an explicit deterministic override such as offline browser acceptance. Ports 5175/8010 avoid pre-existing services on 5173/8000. Logs, PostgreSQL binaries/data, and generated credentials are in the ignored `.runtime/` directory. App credentials are in ignored `backend/.env`.

Use fictional patients only. Demo doctor access is explicitly enabled locally; production staff authentication and patient access tokens are not implemented. UUID-based session access is for this local demo, not an authorization scheme.

Stop the app, retaining the database:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/stop-dev.ps1
```

Stop the app and database, retaining all data:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/stop-dev.ps1 -Database
```

Windows Application Control currently blocks this machine's PostgreSQL control executable. While an approved database is already running, use `scripts/start-dev.ps1 -UseRunningDatabase` to start only the application services; add `-NormalizationProvider mock` only when that override is intended. Full database restart acceptance remains pending resolution through Windows security policy.

Structured data is in PostgreSQL database `medikiosk`, schema `public`: `patients`, `sessions`, `consents`, interview/answer and normalization tables, `alerts`, `documents`, `document_extractions`, `medication_fact`, `lab_fact`, `medical_fact_revisions`, summaries, and audit records. The timeline is computed from source facts; the older generic `timeline_fact` table is an unused compatibility scaffold. Uploaded file bytes are in the configured local upload directory; PostgreSQL stores their object keys, hashes and metadata. Database files are under ignored `.runtime/pgdata`; inspect records through SQL or a database client rather than editing those files.

See [setup](docs/setup.md) for fresh installation and manual commands, [testing](docs/testing.md) for acceptance checks, and [implementation status](docs/implementation-status.md) for results and next work.

## Development rules

Read [CLAUDE.md](CLAUDE.md), the [decision log](docs/decisions.md), and the [roadmap](docs/roadmap.md) before making changes. Structured data remains canonical. Consent and verification are controlled by the backend. Unknown information must remain unknown. Preserve source wording and the doctor's review history.
