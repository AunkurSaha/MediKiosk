# Implementation Roadmap — MediKiosk

Do not jump phases merely because later phases are more impressive.

Each phase should leave the repository runnable.

Current status: **Phase 7 complete for the local synthetic-data prototype**. Phase 1–3 foundations remain; Phase 4–6 remediation and the continuing PostgreSQL process-restart limitation are tracked in [stabilization status](stabilization-implementation-status.md). Phase 8 is not authorized or implemented.

The sections below describe historical or future scope, not current acceptance. Phase 3B and 4B live integrations remain unaccepted; Phase 6 has storage and explicit mock fixtures, not real OCR.

## Phase 0 — Repository context

Status: starter documents supplied.

Deliver:
- repo/docs initialized;
- environment conventions;
- gitignore;
- basic setup documentation.

## Phase 1 — Deterministic end-to-end foundation

Goal:

```text
Patient enters
→ creates session
→ grants consent
→ answers deterministic questions
→ data stored
→ doctor sees data
→ doctor edits/confirms review
```

Deliver:
- React app;
- FastAPI app;
- PostgreSQL;
- migrations;
- patient/doctor route skeleton;
- language/identification/consent/interview/complete UI;
- doctor session list/detail;
- summary edit/confirm;
- audit events for key actions;
- tests.

No AI, OCR, voice, red flags, FHIR, or ABDM required.

Exit criteria:
- fresh setup works;
- data survives backend restart with database;
- doctor can see exactly what patient entered;
- confirmation state persists;
- checks pass.

## Phase 2 — Structured adaptive interview

Status: implemented; deterministic API, UI, PostgreSQL, browser and restart checks are documented in the implementation status.

Add:
- explicit deterministic complaint selection (normalization deferred to Phase 3);
- question-flow config;
- five complaint families;
- required field completion;
- branch logic;
- structured clinical history builder;
- separate AYUSH demonstration question configuration.

Store configs in `ai/complaint_flows/`.

Exit criteria:
- deterministic tests prove next-question behavior;
- no uncontrolled LLM interview.

## Phase 3A — Provider-neutral normalization

Status: complete and verified with deterministic mock, strict schemas, explicit field eligibility, failure fallback, durable provenance, source invalidation, UI and migration/restart tests. No external credentials or API calls.

## Phase 3B — NVIDIA adapter
Implemented behind the existing interface. Offline coverage retained; reliable live acceptance remains open. See the reconciled status report.

## Phase 4A — Voice and question playback
Implemented with mocks; server candidate/consent/provenance and audio cleanup remediation is part of stabilization.

## Phase 4B — BHASHINI adapter
Mocked adapter verification only. No demonstrated live acceptance; native browser audio conversion remains unverified.

## Phase 5 — Prototype red flags and triage
Implementation is under stabilization. Staff identity, WebSocket admission/delivery, source polarity/context and alert reconciliation must satisfy the acceptance matrix. No clinical validation is claimed.

## Phase 6 — Documents
Local storage, content validation, typed parser fixtures and doctor review are implemented/remediated. Real OCR remains absent. No new OCR provider is authorized during stabilization.

## Phase 7 — Medical extraction + timeline + discrepancies

Status: complete for deterministic synthetic-fixture scope. Medication/lab materialization, current-fact services, computed timeline, conservative discrepancy checks, additive fact review history, staff-only APIs, doctor UI, and acceptance coverage are implemented. The generic timeline table remains an unused compatibility scaffold. See [Phase 7 report](phase7-implementation-status.md).

Delivered:
- medication/lab extraction;
- regex + structured AI extraction where useful;
- normalized facts;
- chronological timeline;
- patient-vs-document discrepancy detection;
- verification status.

## Phase 8 — Draft summary

Add:
- summary provider;
- summary from structured facts;
- explicit unknowns;
- generated draft preservation;
- doctor editor improvements.

## Phase 9 — Doctor verification hardening

Add:
- field-level verification where useful;
- versioning/revisions;
- better audit;
- document/source cross-reference.

## Phase 10 — FHIR export

Add:
- mappings;
- FHIR validation;
- export screen/API;
- tests against representative records.

Do not block internal implementation on FHIR schema too early.

## Phase 11 — ABDM / HIS demonstration

Add only after core flow works:
- ABDM sandbox connector where credentials/onboarding allow;
- otherwise a clearly labeled mock/sandbox integration demonstration;
- architecture showing HIS interoperability.

## Phase 12 — Demo polish

Add:
- seeded showcase patient;
- Bengali chest-pain scenario;
- realistic loading states;
- kiosk full-screen polish;
- judge-friendly triage alert;
- timeline visuals;
- FHIR export preview;
- reset demo command.

## Priority rule

If a later feature is blocked, preserve the complete flow with a transparent mock rather than pretending the integration works.
