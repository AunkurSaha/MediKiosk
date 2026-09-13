# Implementation Roadmap — MediKiosk

Do not jump phases merely because later phases are more impressive.

Each phase should leave the repository runnable.

Current status: **Phase 12 complete for the local synthetic-data prototype**, with the active interview architecture updated by ADR-027 to use grounded per-turn RAG planning over deterministic coverage and safety controls. Current limitations are tracked in [implementation status](implementation-status.md).

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

Status: implemented. The flow remains the deterministic coverage/type/branch/completion policy; ADR-027 now permits grounded RAG to select and word one approved missing field per turn after chief-complaint acquisition.

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

Status: complete for deterministic synthetic-fixture scope. Medication/lab materialization, current-fact services, computed timeline, conservative discrepancy checks, additive fact review history, staff-only APIs, doctor UI, and acceptance coverage are implemented. The generic timeline table remains an unused compatibility scaffold. See [Phase 7 report](implementation-status.md).

Delivered:
- medication/lab extraction;
- regex + structured AI extraction where useful;
- normalized facts;
- chronological timeline;
- patient-vs-document discrepancy detection;
- verification status.

## Phase 8 — Draft summary

Status: complete for deterministic prototype scope. Clinician-controlled clinical summary drafting, 10 fixed structured sections, explicit unknowns, evidence source attribution, doctor review/edit workspace, optimistic revision history, and immutable confirmation locking are implemented. No LLM or ungrounded generative AI is used. See [Phase 8 report](implementation-status.md).

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

Status: complete for deterministic prototype scope. Granular field-level verification, versioned confirmed-summary clinical amendments, append-only session audit trails, and bidirectional cross-referencing are implemented. See [Phase 9 report](implementation-status.md).

Delivered:
- field-level verification service and badge component supporting granular status tracking (`unverified`, `verified`, `flagged`) with optimistic locking and synchronization to interview answers;
- append-only `field_verification_revisions` tracking clinician reviewer provenance;
- confirmed summary amendment workflow (`POST /summary/amend`) preserving original confirmed records intact while attaching official versioned addenda with mandatory clinician justification;
- comprehensive session audit trail service and viewer (`GET /audit-trail`) tracking patient, staff, and system actions with actor-based filtering;
- bidirectional document and clinical fact cross-reference engine (`GET /cross-references`) displayed in DocumentViewer and SummaryWorkspace;
- strict anti-forgery protection rejecting client-supplied reviewer identities.

## Phase 10 — FHIR export

Status: complete for deterministic prototype scope. Decoupled pure Pydantic v2 HL7 FHIR R4 export architecture, LOINC 34105-7 Composition document bundles, collection bundles, reference integrity validation, non-diagnostic provisional condition guardrails, and doctor export UI with JSON preview and download are implemented. See [Phase 10 report](implementation-status.md).

Delivered:
- decoupled adapter layer (`FHIRAdapterService`) leaving internal relational schemas intact;
- robust pure Pydantic v2 HL7 FHIR R4 resource models (`Patient`, `Encounter`, `QuestionnaireResponse`, `Condition`, `MedicationStatement`, `Observation`, `DocumentReference`, `Composition`, `Bundle`, `OperationOutcome`);
- standard FHIR Document Bundle (`type: "document"`) with LOINC `34105-7` Composition clinical summary as `entry[0]`, alongside alternative Collection Bundle (`type: "collection"`);
- deterministic validation engine verifying document bundle invariants and internal `urn:uuid:...` reference integrity;
- strict non-diagnostic boundary: `Condition` resources represent provisional patient-reported symptoms and complaints only (`verificationStatus: "provisional"`, note: "Non-diagnostic. Requires clinical assessment");
- doctor export and validation endpoints (`GET /fhir/export`, `GET /fhir/bundle`, `POST /fhir/validate`) with staff identity enforcement and audit logging (`FHIR_EXPORTED`, `FHIR_BUNDLE_ACCESSED`);
- doctor workspace `FHIRExportModal` component featuring format toggle, validation badge, resource breakdown inventory pills, syntax-styled JSON preview, clipboard copy, and `.json` file download;
- comprehensive automated test suites (5 backend integration tests, 6 frontend component tests) with zero regressions across the codebase.

## Phase 11 — ABDM / HIS demonstration

Status: complete for deterministic prototype scope. National Health Stack M1 ABHA verification, M2 care context linking, M3 FHIR document bundle data exchange, outbound hospital information system (HIS) dispatcher, kiosk inline ABHA verification, and doctor ABDM & HIS hub modal are implemented. See [Phase 11 report](implementation-status.md).

Delivered:
- ABDM sandbox & mock gateway engine (`ABDMService`) supporting format validation and simulated OTP/demographic auth for 14-digit ABHA numbers and ABHA handles;
- M1 ABHA identity verification with persistent `Patient.demo_abha_id` sync and `ABDMRecord` tracking;
- M2 HIP Care Context Linking engine (`link_care_context`) creating deterministic `medikiosk_ctx_<id>` references bound to hospital tokens;
- M3 Health Information Exchange packaging Phase 10 HL7 FHIR R4 Document Bundles for downstream consumption;
- outbound Hospital Information System (HIS / EMR) dispatcher (`HISService`) with configurable endpoint or local simulated gateway generating verifiable receipts (`HIS-ACK-...`);
- kiosk onboarding step inline ABHA verification button (`Verify`) with live status feedback;
- doctor workspace `ABDMHISModal` component providing unified M1 verification, M2 care context linking, and HIS dispatch controls;
- dedicated database persistence (`abdm_records` table, Alembic migration `8b4e9c2d1f73`);
- comprehensive automated test coverage (5 backend integration tests, 5 frontend component tests) with zero regressions across 350 backend tests and 84 frontend tests.

## Phase 12 — Demo polish

Status: complete for deterministic prototype scope. Canonical Bengali chest-pain showcase patient seeding, demo management CLI and API endpoints, kiosk full-screen toggle, judge-friendly emergency triage alert presentation, and doctor workspace demo tools are implemented. See [Phase 12 report](implementation-status.md).

Delivered:
- canonical Bengali (bn) chest-pain showcase patient with all 26 applicable flow answers, 2 deterministic emergency/urgent safety alerts, 2 previewable mock-fixture documents with source-linked facts, ABDM M1/M2/HIS mock state, and a revisioned 10-section clinical summary;
- `ShowcaseService` with idempotent transactional seeding and database reset plus document-file cleanup;
- `seed.py` CLI: `--showcase` and `--reset` flags;
- demo management API endpoints (`POST /demo/seed-showcase`, `POST /demo/reset`) gated by `DEMO_MODE` and doctor auth;
- kiosk full-screen toggle button and one-click showcase loader;
- doctor workspace seed/reset quick actions with confirmation and feedback;
- enhanced emergency triage alert banners with high-visibility badges;
- comprehensive automated test coverage (6 backend integration tests, 8 frontend component tests, and a dedicated browser showcase journey) with zero regressions across 356 SQLite backend tests, 98 frontend component tests, and 29 Chromium E2E journeys.

## Priority rule

If a later feature is blocked, preserve the complete flow with a transparent mock rather than pretending the integration works.

