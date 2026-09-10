# Phase 8 implementation status — 2026-09-10

Phase 8 is implemented for the **local prototype**. It adds a deterministic, clinician-controlled clinical draft summary engine, source evidence attribution, an append-only revision history with explicit actor classification, doctor editing with optimistic conflict controls, and irreversible confirmation locking. It uses no LLM and makes no diagnostic assertions.

## Implemented workflow

```text
Patient Interview
      +
Normalization (Offline dictionary / verified concepts)
      +
Medical Facts (Medications + Labs from Structured Documents)
      +
Timeline (Deterministic chronological & unknown-date events)
      +
Discrepancies (Conservative comparison rules)
      +
Safety Alerts (Deterministic red-flag rules)
      ↓
ClinicalSummaryService (Deterministic template synthesis)
      ↓
Immutable Machine Draft (generated_text + generated_structured_json)
      ↓
Doctor Working Draft (reviewed_text + optimistic expected_version + review_notes)
      ↓
Append-Only Revision Feed (summary_revisions: DOCTOR vs SYSTEM actor provenance)
      ↓
Clinician Confirmed Summary (confirmed_text, confirmed_by, confirmed_at — locked immutable)
```

## Summary structure (10 fixed sections)

The summary drafting engine produces 10 structured sections with deterministic content:

1. **Patient Information**: Age, gender, intake language, session start timestamp.
2. **Chief Complaint**: Stated primary complaint, validated complaint family, and onset/duration.
3. **History of Present Illness (HPI)**: Structured findings from adaptive interview questions (e.g. chest pain characteristics, radiation, fever duration, respiratory symptoms) with explicit answer values and labels. Includes AYUSH demonstration disclaimer when an AYUSH pathway is active.
4. **Relevant Medical History**: Chronic conditions, hypertension/diabetes history, known surgeries, and allergy disclosures with explicit negative/positive reporting.
5. **Current Medications**: Patient-reported medications synthesized with active document medication facts, dosages, frequencies, and verification statuses.
6. **Investigations / Laboratory Findings**: Materialized document lab results with observed values, units, reference ranges, abnormal flags, and source document filenames.
7. **Clinical Timeline**: Chronological events derived from explicit clinical dates, plus a dedicated section for clinically relevant facts lacking explicit calendar dates (unknown date status).
8. **Safety Alerts**: Active and acknowledged red-flag safety screening alerts, trigger codes, rule reasons, and detection timestamps.
9. **Potential Discrepancies**: Deterministically detected conflicts between patient-reported statements and uploaded medical documents (e.g. omitted medications, dosage conflicts, lab value variances), explicitly labeled as requiring clinician review.
10. **Unknown / Not Reported Information**: Clinical domains explicitly skipped, unanswered, or unassessed during intake, preventing default assumptions or silent omissions.

## Source evidence attribution

Every statement in the structured summary retains full traceability through an `EvidenceReference` model:
- `statement_id`: Stable identifier for the generated statement.
- `section`: Target summary section (e.g. `history_present_illness`, `current_medications`, `investigations_labs`).
- `statement_text`: Rendered consultation text.
- `source_type`: Attribution category (`patient_answer`, `normalized_fact`, `medical_fact`, `document`, `alert`, `discrepancy`).
- `source_id`: UUID or identifier of the underlying source record.
- `source_text`: Exact raw text or value extracted from the source.
- `source_metadata`: Contextual metadata (e.g., document filename, question key, rule ID, verification status).

Doctors can trace any summary statement directly back to its origin via `GET /api/doctor/sessions/{session_id}/summary/evidence` or in the frontend Evidence view.

## 4-Stage lifecycle & immutability

1. **Machine Draft**:
   - `generated_text` (markdown consultation draft) and `generated_structured_json` (typed section hierarchy and evidence references).
   - Generated automatically when an intake session completes, or explicitly regenerated via `POST /api/doctor/sessions/{session_id}/summary/regenerate`.
   - Immutable snapshot that is never overwritten by doctor edits.
2. **Doctor Working Draft**:
   - Stored in `reviewed_text`.
   - Initialized to `generated_text` upon intake completion.
   - Doctor edits via `PUT /api/doctor/sessions/{session_id}/summary` update `reviewed_text` and increment `draft_version`.
   - Uses optimistic concurrency control (`expected_version`).
   - If manual doctor edits exist, attempting regeneration without `confirm_replacement: true` returns HTTP 409 (`CONFIRM_REPLACEMENT_REQUIRED`).
3. **Append-Only Revision History**:
   - Each state transition creates a permanent `summary_revisions` record.
   - Captures `revision_type` (`GENERATED`, `EDITED`, `CONFIRMED`), `actor_type` (`SYSTEM` vs `DOCTOR`), `actor_user_id` (server-authenticated, not client-forged), `review_notes`, and structured/text snapshots.
4. **Confirmed Summary**:
   - Finalized via `POST /api/doctor/sessions/{session_id}/summary/confirm`.
   - Copies effective working draft into `confirmed_text`, stamps `confirmed_by` and `confirmed_at`, sets `status = confirmed`, and closes the intake session.
   - Irreversible lock: subsequent `PUT` or `regenerate` calls return HTTP 409 (`CONFIRMED_IMMUTABLE`).

## Database migrations

- Migration `1915850a59d1_phase8_draft_summary.py`:
  - `clinical_summaries`: adds `confirmed_text` (Text, nullable), `draft_provider` (String 64, default 'deterministic_template'), `draft_version` (Integer, default 1).
  - `summary_revisions`: adds `revision_type` (String 32, default 'EDITED'), `actor_type` (String 32, default 'DOCTOR'), `review_notes` (Text, nullable), `structured_snapshot` (JSONB / SQLite JSON, nullable), and relaxes `actor_user_id` to nullable (enabling system-authored generation revisions).
- Verified via `scripts/verify-phase8-migrations.py` against PostgreSQL and SQLite:
  - Empty database upgrade to head passes.
  - Phase 7 to Phase 8 additive upgrade passes.
  - Isolated downgrade/reupgrade passes.
  - Pre-existing row fingerprint integrity preserved.
  - Alembic model-versus-schema comparison clean.

## Doctor APIs

All summary endpoints reside under `/api/doctor`:
- `GET /api/doctor/sessions/{session_id}/summary`: Returns full summary state (`generated_text`, `reviewed_text`, `confirmed_text`, `draft_version`, `status`, `structured_summary`, `evidence`).
- `PUT /api/doctor/sessions/{session_id}/summary`: Saves doctor working draft with optimistic locking (`expected_version`) and optional `review_notes`.
- `POST /api/doctor/sessions/{session_id}/summary/regenerate`: Re-runs deterministic summary drafting against latest facts, requiring `confirm_replacement` if manual edits exist.
- `POST /api/doctor/sessions/{session_id}/summary/confirm`: Confirms and permanently locks the summary, emitting an audit event.
- `GET /api/doctor/sessions/{session_id}/summary/revisions`: Returns complete chronological revision history.
- `GET /api/doctor/sessions/{session_id}/summary/evidence`: Returns source evidence attribution references.

## Frontend Summary Workspace

- Upgraded doctor workspace with a dedicated `SummaryWorkspace` component:
  - **Summary Editor**: Markdown consultation draft textarea, save draft button, version badge, review notes input, regeneration button with conflict modal, and confirmation button.
  - **Evidence Attribution Tab**: Interactive table mapping each consultation statement to its source type, source ID, and raw source text.
  - **Revision History Tab**: Chronological audit feed displaying revision type, actor badge (`DOCTOR` vs `SYSTEM`), timestamp, version, review notes, and snapshot previews.
  - **Confirmed Summary View**: Read-only finalized presentation with confirmation timestamp, clinician attribution, and disabled editing controls.

## Verification results

- **Backend**: **335 tests** pass (15 comprehensive Phase 8 tests in `backend/tests/test_phase8_summary.py` + 320 regression tests).
  - Deterministic drafting across complaint families.
  - All 10 structured sections and unknowns verified.
  - Evidence references verified for every section.
  - Revision history and optimistic locking verified.
  - Regeneration conflict gating verified.
  - Confirmation locking and immutability verified.
  - Rejection of forged actor identity and unauthorized access verified.
- **Backend Lint**: `ruff check app tests` passes with zero warnings or errors.
- **Frontend Tests**: **67 tests** pass across 8 test suites (including 6 new component tests in `frontend/src/test/phase8.test.tsx`).
- **Frontend Lint & Build**: `npm run lint` passes with zero errors/warnings; `npm run build` generates production bundle cleanly.

## Non-negotiable clinical safety boundaries

- **No AI Doctor / No LLM**: Summary engine is 100% deterministic code. No external generative models are invoked.
- **No Diagnostic Claims**: The system never generates diagnostic statements (e.g. "Diagnosis: Acute Coronary Syndrome").
- **No Treatment Recommendations**: The system never prescribes medications, dosage alterations, or clinical therapies.
- **No Hallucinated Dates or Facts**: Timeline dates and clinical observations only appear if explicitly documented. Missing values are explicitly marked unknown.
- **Human Clinical Authority**: Doctor review and confirmation are required before any summary is marked confirmed.

## Explicit prototype limitations

- Real OCR remains **not implemented** (uses content-addressed synthetic document fixtures).
- FHIR export is deferred to **Phase 10**.
- ABDM and hospital information system (HIS) integration is deferred to **Phase 11**.
- Production authentication / OAuth is not implemented (uses demo staff headers).
- The PostgreSQL process restart limitation under Windows Application Control (WDAC) remains an existing documented environment constraint and was not modified.
