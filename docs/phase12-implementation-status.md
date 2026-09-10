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
