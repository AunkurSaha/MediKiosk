# Phase 7 implementation status — 2026-09-10

Phase 7 is implemented for the **local synthetic-data prototype**. It adds source-linked medication/lab facts, a deterministic computed timeline, conservative discrepancy checks, additive fact review history, and dedicated doctor UI. It does not add Phase 8 summary AI.

## Implemented flow

```text
content-addressed synthetic document fixture
→ existing typed StructuredDocument validation
→ atomic medication/lab fact materialization
→ staff-only current-fact service
→ deterministic computed timeline and discrepancy evaluation
→ doctor fact/timeline/discrepancy UI
→ optimistic verify/reject/correct review
→ original extraction plus additive revision retained
```

### Medical facts and review

- `MedicalFactService` returns medication and lab facts in stable order, excludes facts whose source extraction was rejected, separates active and rejected fact rows, and retains document/extraction/raw-source references.
- Medication values support explicit name, dosage, unit, route, frequency, duration, start/end dates, and instructions. Lab values support explicit test, value, unit, reference range, source flag, and observation time. Unknown values stay null.
- Additive migration `d12f4a7b9c31` adds the missing medication fields, optimistic `review_version`, and `medical_fact_revisions`.
- A correction never overwrites machine-extracted clinical fields. Each review revision stores the original value, the complete effective corrected value when applicable, server-owned reviewer ID, status, notes, version, and time.
- Confirmed/cancelled sessions are immutable; stale versions, anonymous callers, forged reviewer fields, and review of rejected sources fail closed.

### Timeline

Phase 7 chose a **computed timeline from source facts**. The older generic `timeline_fact` table remains an unused compatibility scaffold and is not populated.

- Explicit document dates, medication start/end dates, and lab observation times produce known-date entries.
- Facts without an explicit clinical date appear in a separate `unknown_date` collection and doctor UI section.
- Dates are never borrowed from upload time or invented. Known entries sort ascending by explicit time with stable deterministic tie-breakers; unknown entries use a stable type/label/source order.
- Every entry carries an event type, canonical label, date status/precision, source reference, raw source when available, and verification status.

### Discrepancies

`DiscrepancyService` is deterministic and uses no LLM. It emits only explainable, source-linked, open items labeled `requires_clinician_review`:

- `MEDICATION_MISSING_FROM_PATIENT_REPORT` when an explicit patient list/no-medication answer omits a document medication;
- `MEDICATION_MISMATCH` only when the same explicitly named medication has comparable, differing dosage text;
- `ALLERGY_CONFLICT` only when patient evidence and an explicit structured document allergy/no-known-allergy statement conflict;
- `LAB_VALUE_CONFLICT` only for two different document sources with the same explicit test, observation time, and unit but different values.

Missing or structurally incomparable evidence produces no discrepancy. Outputs do not infer diagnosis, adherence, treatment significance, or prescribing error.

### APIs and UI

All endpoints reuse existing staff authorization:

- `GET /api/doctor/sessions/{id}/medical-facts`
- `GET /api/doctor/sessions/{id}/timeline`
- `GET /api/doctor/sessions/{id}/discrepancies`
- `PATCH /api/doctor/sessions/{id}/medical-facts/medications/{fact_id}`
- `PATCH /api/doctor/sessions/{id}/medical-facts/labs/{fact_id}`

The doctor workspace has dedicated Medical facts, Timeline, and Discrepancies sections with loading/error/empty states, responsive layout, source-document links, raw source, verification badges, correction controls, and cautious “Possible discrepancy — requires clinician review” wording.

## Verification

- Backend: **331 tests** pass on SQLite and **331 tests** pass on PostgreSQL; Ruff passes.
- Frontend: **61 component tests** pass; ESLint, Prettier, TypeScript, and Vite build pass.
- Playwright: **27 browser tests** pass, including four Phase 7 journeys for source-linked prescription facts, lab null handling/mobile layout, known/unknown timeline sections, possible discrepancies, and verify/reject/correct review with original source retained.
- PostgreSQL migration verifier passes empty and prior-revision upgrades, isolated downgrade/reupgrade, application-database upgrade, pre-existing row fingerprints, and Alembic model/schema comparison.
- Configured-secret/dependency audits pass within their documented scope.
- Application-only restart/resume passes against the existing PostgreSQL process.

## Explicit limitations

- Real OCR is **not implemented**. Only current content-addressed synthetic fixtures yield mock typed extraction; arbitrary valid uploads remain extraction-unavailable.
- No new OCR or LLM provider was added. All Phase 7 timeline/discrepancy decisions are deterministic prototype logic.
- No clinical validation is claimed for extraction, comparison rules, UI wording, or fixtures.
- No production readiness, production authentication, regulatory compliance, diagnosis, treatment recommendation, FHIR, or ABDM claim is made.
- Source page/region remains null when not supplied; the system never invents coordinates.
- The full PostgreSQL process-restart gate remains **blocked by Windows Application Control**, which prevents `pg_ctl.exe` execution. Application services were restarted against the existing database; this is not full PostgreSQL restart verification. WDAC was not modified.
