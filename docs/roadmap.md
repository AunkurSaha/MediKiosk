# Implementation Roadmap — MediKiosk

Do not jump phases merely because later phases are more impressive.

Each phase should leave the repository runnable.

Current status: **Phase 9 complete for the local synthetic-data prototype**. Phase 1–3 foundations remain; Phase 4–6 remediation and the continuing PostgreSQL process-restart limitation are tracked in [stabilization status](stabilization-implementation-status.md).

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

Status: complete for deterministic prototype scope. Clinician-controlled clinical summary drafting, 10 fixed structured sections, explicit unknowns, evidence source attribution, doctor review/edit workspace, optimistic revision history, and immutable confirmation locking are implemented. No LLM or ungrounded generative AI is used. See [Phase 8 report](phase8-implementation-status.md).

Delivered:
- deterministic `ClinicalSummaryService` synthesizing intake answers, normalized facts, medication/lab medical facts, computed timeline, discrepancies, and red-flag alerts;
- 10 fixed structured sections with strict preservation of unknown/unreported information;
- source evidence attribution (`EvidenceReference`) mapping summary statements to underlying records;
- strict 4-stage summary model: immutable machine draft, doctor working draft, append-only revision history (`summary_revisions`), and confirmed immutable summary;
- optimistic locking (`expected_version`) and explicit conflict resolution on regeneration;
- server-attributed confirmation locking (`confirmed_text`, `confirmed_by`, `confirmed_at`) rejecting subsequent edits/regeneration;
- doctor Summary Workspace UI with multi-tab Editor, Evidence Attribution viewer, and Revision History feed;
- zero diagnostic claims, zero treatment recommendations, zero medication modifications, and zero invented dates/facts.

## Phase 9 — Doctor verification hardening

Status: complete for deterministic prototype scope. Granular field-level verification, versioned confirmed-summary clinical amendments, append-only session audit trails, and bidirectional cross-referencing are implemented. See [Phase 9 report](phase9-implementation-status.md).

Delivered:
- field-level verification service and badge component supporting granular status tracking (`unverified`, `verified`, `flagged`) with optimistic locking and synchronization to interview answers;
- append-only `field_verification_revisions` tracking clinician reviewer provenance;
- confirmed summary amendment workflow (`POST /summary/amend`) preserving original confirmed records intact while attaching official versioned addenda with mandatory clinician justification;
- comprehensive session audit trail service and viewer (`GET /audit-trail`) tracking patient, staff, and system actions with actor-based filtering;
- bidirectional document and clinical fact cross-reference engine (`GET /cross-references`) displayed in DocumentViewer and SummaryWorkspace;
- strict anti-forgery protection rejecting client-supplied reviewer identities.

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
