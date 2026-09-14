# MediKiosk

MediKiosk is a local SIH prototype for pre-consultation intake. The patient supplies a structured history; a doctor reviews, edits, and confirms it. It does not diagnose or prescribe.

The [roadmap](docs/roadmap.md), [architecture](docs/architecture.md), and [implementation status](docs/implementation-status.md) describe the current scope and system boundaries.

## Current working scope

Phases 1–12 are implemented for the local synthetic-data prototype: deterministic intake, optional normalization, mock speech, deterministic safety alerts, document storage/typed fixture extraction, source-linked evidence and timeline, doctor-controlled summaries and amendments, FHIR R4 export, mock ABDM/HIS interoperability, and a seeded Bengali showcase journey.

The draft is a deterministic rendering of saved answers. Back/edit preserves prior source answers; resume uses the pinned flow and cursor. Confirmed records are locked. Doctor review remains separate from machine output.

Real OCR is not implemented. Sarvam REST ASR/TTS has a successful synthetic Bengali TTS-to-ASR loopback, but physical microphone and accent acceptance is not established. BHASHINI live ASR/TTS is not demonstrated. NVIDIA live evidence is mixed and does not establish reliable acceptance. Rules, question wording, translations, extraction fixtures, and discrepancy comparisons are prototype content without clinical validation. See the [current implementation status](docs/implementation-status.md) for evidence and limitations.

## Run on this configured Windows machine

From PowerShell in the project root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-dev.ps1 -SkipSeed
```

- App: http://127.0.0.1:5175
- Doctor workspace: http://127.0.0.1:5175/doctor
- API docs: http://127.0.0.1:8010/docs
- Database: configured Supabase project

The launcher starts hidden application processes, applies migrations to Supabase, and uses the providers selected in `backend/.env`. Omit `-SkipSeed` only when the synthetic demo fixtures need to be created or refreshed. Ports 5175/8010 avoid pre-existing services on 5173/8000. Logs are in the ignored `.runtime/` directory. Supabase credentials are backend-only in ignored `backend/.env`.

Use fictional patients only. Demo doctor access is explicitly enabled locally; production staff authentication and patient access tokens are not implemented. UUID-based session access is for this local demo, not an authorization scheme.

Stop the app, retaining the database:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/stop-dev.ps1
```

Structured data is in the configured Supabase PostgreSQL database, schema `public`: `patients`, `sessions`, `consents`, interview/answer and normalization tables, `alerts`, `documents`, `document_extractions`, `medication_fact`, `lab_fact`, `medical_fact_revisions`, summaries, and audit records. The timeline is computed from source facts. Uploaded file bytes remain in the configured local upload directory; Supabase stores their object keys, hashes and metadata.

See [setup](docs/setup.md) for fresh installation and manual commands, [testing](docs/testing.md) for acceptance checks, and [implementation status](docs/implementation-status.md) for results and next work.

## Development rules

Read [AGENTS.md](AGENTS.md), the [decision log](docs/decisions.md), and the [roadmap](docs/roadmap.md) before making changes. Structured data remains canonical. Consent and verification are controlled by the backend. Unknown information must remain unknown. Preserve source wording and the doctor's review history.
