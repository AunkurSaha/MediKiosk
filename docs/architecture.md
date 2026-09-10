# Architecture — MediKiosk

Current implementation is Phase 8; see the implemented boundaries at the end and [status](phase8-implementation-status.md). The broader module/deployment diagrams describe the target roadmap, including unimplemented future integrations.

## 1. Architectural style

For the SIH prototype, use a **modular monolith**:

- one React frontend;
- one FastAPI backend;
- one PostgreSQL database;
- optional MinIO object storage;
- internal modules/adapters for AI and integration providers.

Do not deploy every conceptual “service” independently.

## 2. Logical architecture

```text
┌──────────────────────────────────────────────────────────────┐
│                       React Frontend                         │
│                                                              │
│   /kiosk/*              /doctor/*              /triage/*     │
│   Patient UI            Doctor UI              Staff UI      │
└──────────────────────────────┬───────────────────────────────┘
                               │
                         REST / WebSocket
                               │
┌──────────────────────────────▼───────────────────────────────┐
│                        FastAPI Backend                       │
│                                                              │
│  API layer                                                   │
│      │                                                       │
│      ├── Session / Identity / Consent                        │
│      ├── Interview Engine                                    │
│      ├── Clinical Normalization Adapter                      │
│      ├── Safety / Red-Flag Engine                            │
│      ├── Speech Adapter                                      │
│      ├── Document / OCR / Extraction Pipeline                │
│      ├── Timeline + Discrepancy Engine                       │
│      ├── Summary Generator                                   │
│      ├── Doctor Verification                                 │
│      ├── FHIR Adapter                                        │
│      └── Audit                                               │
└───────────────┬───────────────────────┬──────────────────────┘
                │                       │
          PostgreSQL               MinIO/S3
       structured data          original documents
```

## 3. Frontend architecture

Use one Vite application with route namespaces.

Suggested feature boundaries:

```text
frontend/src/
├── app/
├── routes/
│   ├── kiosk/
│   ├── doctor/
│   └── triage/
├── features/
│   ├── identification/
│   ├── consent/
│   ├── interview/
│   ├── documents/
│   ├── alerts/
│   ├── timeline/
│   └── summary/
├── components/
├── api/
├── types/
└── i18n/
```

Avoid duplicating clinical types separately in many files. Keep API response types centralized.

## 4. Backend modules

Suggested:

```text
backend/app/
├── main.py
├── api/
│   ├── health.py
│   ├── patients.py
│   ├── sessions.py
│   ├── consent.py
│   ├── interview.py
│   ├── documents.py
│   ├── alerts.py
│   ├── doctor.py
│   └── exports.py
├── core/
│   ├── config.py
│   ├── security.py
│   └── logging.py
├── db/
│   ├── base.py
│   └── session.py
├── models/
├── schemas/
└── services/
    ├── interview_engine.py
    ├── clinical_normalizer.py
    ├── red_flag_engine.py
    ├── speech.py
    ├── ocr.py
    ├── document_extractor.py
    ├── timeline.py
    ├── discrepancies.py
    ├── summarizer.py
    ├── fhir.py
    └── audit.py
```

## 5. Canonical clinical representation

The most important architectural rule:

**Raw patient text is not the canonical record. Generated prose is not the canonical record.**

The canonical representation is structured data.

Conceptual shape:

```json
{
  "session_id": "uuid",
  "chief_complaints": [],
  "hpi": {},
  "past_medical_history": [],
  "past_surgical_history": [],
  "medications": [],
  "allergies": [],
  "family_history": [],
  "personal_history": {},
  "review_of_systems": {},
  "document_facts": [],
  "alerts": [],
  "discrepancies": []
}
```

The exact schema can evolve, but every external AI output must be converted into validated structured fields before downstream use.

## 6. Interview pipeline

```text
Patient answer
→ preserve raw/original answer
→ normalize into known clinical field(s)
→ validate against schema
→ update structured history
→ run safety rules
→ determine missing required fields
→ select next question
```

Question selection should use:
- complaint-flow configuration;
- completion state;
- deterministic branch rules;
- optional language-generation/normalization help.

## 7. Speech architecture

Use an interface:

```text
SpeechService
├── transcribe(audio, language)
└── synthesize(text, language)
```

Possible implementations:
- mock;
- BHASHINI;
- AI4Bharat/self-hosted;
- another explicitly approved provider.

Frontend should not depend on provider-specific API shape.

## 8. Red-flag architecture

```text
Structured clinical facts
→ deterministic versioned rules
→ zero or more Alert objects
→ persistence
→ WebSocket event
→ Triage Dashboard
```

Alert must contain:
- rule ID/version;
- severity;
- reason;
- triggering facts;
- created time;
- acknowledgement info.

LLM output alone must never create a non-explainable emergency classification.

## 9. Document pipeline

```text
upload
→ persist original file
→ classify document
→ preprocess image if needed
→ OCR
→ preserve OCR output/confidence
→ structured extraction
→ validation
→ timeline facts
→ discrepancies
→ doctor verification state
```

Object storage should hold source files. PostgreSQL holds metadata and extracted structured facts.

## 10. Summary pipeline

```text
validated structured history
+ validated document facts
+ explicit alert/discrepancy state
→ summary generator
→ structured/draft summary
→ doctor edits
→ doctor confirms
→ confirmed record
```

The summarizer receives structured data, not an uncontrolled full chat dump.

## 11. FHIR boundary (Phase 10)

FHIR is a decoupled adapter layer built on top of the internal clinical data model. Internal persistence does not mirror FHIR; instead, a deterministic transformation engine translates records into standards-compliant HL7 FHIR R4 on demand:

```text
MediKiosk Internal Models
(Patient, Session, InterviewAnswer, MedicationFact, LabFact, Document, ClinicalSummary)
        ↓
FHIRAdapterService.build_bundle()
        ↓
FHIR R4 Resources (Pure Pydantic v2 Models)
        ↓
FHIRAdapterService.validate_bundle()
        ↓
Validated FHIR R4 Bundle (Document / Collection)
        ↓
Doctor UI / HIS / ABDM Connector (Phase 11)
```

### Key Architectural Invariants

1. **Decoupled Transformation**: The database schema remains pure relational PostgreSQL. Resources are generated dynamically and referenced via uniform internal urns (`urn:uuid:<resource_type>-<id>`).
2. **Document Bundle Standard**:
   - For `type: "document"`, HL7 FHIR R4 mandates that `entry[0]` must be a `Composition` resource.
   - The `Composition` resource encodes a Consultation Note (LOINC `34105-7`) structured with sections linking to chief complaint, intake responses, medications, diagnostic tests, and source records.
3. **Strict Non-Diagnostic Clinical Boundary**:
   - `Condition` resources represent provisional, patient-reported complaints and symptoms only.
   - `verificationStatus` is permanently set to `provisional` with category `problem-list-item`.
   - Mandatory non-diagnostic disclaimer note: `"Non-diagnostic. Requires clinical assessment."`
   - Autonomous diagnosis declarations or treatment prescriptions are strictly forbidden.
4. **Internal Reference Integrity**:
   - All references (`subject`, `encounter`, `entry` links) within the bundle are resolved against the `fullUrl` of contained resources.
   - Validated deterministically by `FHIRAdapterService.validate_bundle()` returning standard `OperationOutcome` resources.
5. **Auditing and Doctor Controls**:
   - Access to FHIR export endpoints requires verified doctor identity (`X-Demo-Doctor: true`).
   - Every export triggers durable audit events (`FHIR_EXPORTED`, `FHIR_BUNDLE_ACCESSED`).

## 12. ABDM and Hospital Information System (HIS) Interoperability (Phase 11)

MediKiosk integrates with the Ayushman Bharat Digital Mission (ABDM) National Digital Health ecosystem and hospital OPD information systems through a modular, decoupled architecture.

### Interoperability Architecture Diagram

```text
┌────────────────────────────────────────────────────────┐
│                   Patient Kiosk                        │
│   • Step: Identify                                     │
│   • ABHA Input + Inline "Verify" Action                │
│   • Instant demographic mock verification (M1)         │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│             MediKiosk PostgreSQL Core                  │
│   • Patient (`demo_abha_id`)                           │
│   • Session & Clinical Intake                          │
│   • ABDMRecord (`abdm_records` table)                  │
└──────────────┬───────────────────────────┬─────────────┘
               │                           │
               ▼                           ▼
┌─────────────────────────────┐ ┌────────────────────────┐
│         ABDM Engine         │ │       HIS Engine       │
│  • M1: ABHA Verification    │ │  • Phase 10 FHIR R4    │
│    (OTP / demographic mock) │ │    Document Bundle     │
│  • M2: Care Context Linking │ │  • OPD Intake Dispatch │
│    (`medikiosk_ctx_<id>`)   │ │  • Receipt Generation  │
│  • M3: FHIR Data Exchange   │ │    (`HIS-ACK-...`)     │
└──────────────┬──────────────┘ └──────────┬─────────────┘
               │                           │
               └─────────────┬─────────────┘
                             ▼
┌────────────────────────────────────────────────────────┐
│              Doctor Workspace Hub                      │
│   • "🏥 ABDM & HIS" Modal Hub                          │
│   • Live Verification & Linking Controls               │
│   • One-Click Outbound Dispatch with Receipt Tracking  │
│   • Prominent Sandbox Mock Disclaimers                 │
└────────────────────────────────────────────────────────┘
```

### Key Architectural Invariants

1. **National Health Stack Alignment (M1, M2, M3)**:
   - **Milestone 1 (ABHA Verification)**: Validates standard 14-digit ABHA numbers (`91-XXXX-XXXX-XXXX`) and phr handles (`user@abdm`, `user@sbx`).
   - **Milestone 2 (HIP Care Context Linking)**: Binds MediKiosk OPD intake encounters into standardized Care Contexts (`medikiosk_ctx_<session_prefix>`), associating them with hospital tokens and patient ABHAs.
   - **Milestone 3 (Health Information Exchange)**: Seamlessly packages the Phase 10 HL7 FHIR R4 Document Bundle (LOINC `34105-7` Composition) for electronic health record transmission.
2. **Dedicated Persistence & Audit Trail**:
   - `ABDMRecord` model tracks verification state (`unverified`, `verified`, `mock_verified`), care context reference, linking timestamp, and HIS dispatch receipt.
   - All state transitions append structured events to the session audit trail (`ABHA_VERIFIED`, `ABDM_CARE_CONTEXT_LINKED`, `HIS_DISPATCHED`).
3. **Outbound HIS Dispatcher (`HISService`)**:
   - Transmits clinical intake, patient demographics, triage alerts, and the full FHIR R4 Document bundle to configured hospital endpoints (`HIS_ENDPOINT_URL`).
   - In synthetic/demo mode, provides a simulated gateway acknowledging receipts (`HIS-ACK-<date>-<hash>`).
4. **Transparent Sandbox Demonstration Boundaries**:
   - In accordance with ADR-010, the integration is an operational **ABDM Sandbox Demonstration**.
   - No production NHA gateway credentials or live Aadhaar biometric/OTP verifications are claimed.
   - Clinical safety invariants remain strictly preserved: zero autonomous diagnoses or treatment assertions are transmitted.

## 13. Failure behavior

External provider failure must degrade gracefully:

- ASR fails → touch/type fallback.
- TTS fails → text remains visible.
- LLM fails → deterministic interview continues where possible.
- OCR fails → original document remains available, mark extraction unavailable.
- object storage fails → do not claim upload succeeded.
- WebSocket fails → alerts remain persisted and visible on dashboard refresh.
- ABDM unavailable → local FHIR export still works.

## 13. Deployment

Prototype target:

```text
docker compose
├── frontend
├── backend
├── postgres
└── minio   # when document phase is enabled
```

Redis is intentionally omitted initially.

## 14. Security boundaries

Never expose:
- database credentials to frontend;
- provider secret keys to frontend;
- raw internal stack traces to end users;
- unrestricted document object URLs.

Use backend-authorized access.

## 15. Scalability posture

For SIH, correctness and a complete demo matter more than premature scale.

Module boundaries are chosen so high-load components can be separated later if required.

## Implemented Phase 2 boundary

This historical Phase 2 subsection described the runnable boundary at that milestone. Later sections below supersede it for normalization, voice, alerts, documents, WebSockets, and Phase 7 medical evidence. FHIR and deployment remain future work.

The active path is:

```text
Consent + explicit patient complaint selection
→ validated ai/complaint_flows configuration
→ pinned InterviewRun snapshot/version
→ typed patient answer + append-only persistence
→ pure InterviewEngine applicability/traversal
→ Pydantic ClinicalHistory from active answers
→ deterministic draft + doctor review/confirmation
```

`schemas/flow.py` defines the small declarative language; `services/flow_registry.py` validates it at startup. `services/interview_engine.py` contains pure evaluation and assembly. `services/adaptive.py` manages transactions, cursor/revision, consent, receipts and history reads. FastAPI handlers only dispatch typed requests. The React Interview container and QuestionRenderer render server state by input type; no frontend clinical flow source remains.

Branch evaluation proceeds in configuration order and only considers active answered parent facts. Inactive historical answers cannot activate descendants. Parent corrections preserve all rows. Reactivated branches restore the latest saved values with original provenance; forward traversal exposes them for review.

Each selection pins the validated configuration to prevent later source edits reinterpreting an ongoing record. Request UUID/hash receipts make delayed retries safe even after subsequent corrections. The existing session-row lock serializes mutations. Optimistic interview revisions prevent stale tabs from changing the current answer.

ClinicalHistory has typed canonical sections, raw wording, typed values, explicit missing-information status and answer provenance. It is computed during intake and snapshotted in the existing summary JSON column at completion. Future normalization consumes this structure and produces separately validated facts; it must not replace raw source wording or take over deterministic question selection. See ADR-015 and the [Phase 2 status](phase2-implementation-status.md).

## Implemented Phase 3A normalization boundary

Phase 3A now adds a provider-neutral normalization service with a deterministic local mock; real providers remain deferred. The InterviewEngine is unchanged and never reads normalization to choose questions or evaluate conditions.

Eligible short_text + explicit field policy → immutable reported answer → bounded provider call → strict ProviderResult validation → trusted symptom/qualitative catalog → durable NormalizationResult → additive Fact.normalization in active history. No provider call occurs in route handlers, GET/history reads, replay or confirmation. Typed values and AYUSH bypass language normalization.

The service uses savepoints so failed enrichment writes/reads do not poison the surrounding patient-answer transaction. Explicit statuses distinguish normalized, unknown, unrecognized and unavailable. Provider exceptions are not echoed/logged with patient text. Persisted results attach to immutable answer IDs; current-source/branch filtering is inherited from Phase 2. No automatic reprocessing/backfill changes existing records.

The future candidate helper returns explicit-confirmation suggestions only and has no caller in the current workflow. Vendor adapters must implement cancellable async I/O, structured output and transport timeouts. See ADR-016 and [Phase 3A verification](phase3a-implementation-status.md).

## Implemented Phase 3B NVIDIA NIM normalization provider

Phase 3B integrates NVIDIA Build / NVIDIA NIM hosted inference (`https://integrate.api.nvidia.com/v1`, model: `google/gemma-4-31b-it`) behind the provider-neutral boundary via `NvidiaClinicalNormalizationProvider`:

```text
Eligible patient answer committed
    ↓
NormalizationService (savepoint isolated)
    ↓
NvidiaClinicalNormalizationProvider
    ├── Input minimization: text, language, canonical_field only
    ├── HTTP client: httpx2 with strict transport timeout (8-15s) and 64KB response cap
    ├── Model parameters: temperature=0, stream=false, max_tokens=768, chat_template_kwargs={"enable_thinking": false}
    └── SecretStr authentication: NVIDIA_API_KEY from environment only, never serialized or logged
    ↓
Strict application validation: LiveProviderResult (Schema 1.1)
    ├── concept from authoritative catalog
    ├── evidence: exact contiguous substring of source text
    ├── polarity: explicit "present" | "absent"
    ├── certainty: "certain" | "uncertain"
    └── confidence: null (prohibits synthetic probabilities)
    ↓
normalization_results: snapshot persisted with provider, model, prompt_version, latency_ms, token_usage
    ↓
Active clinical history & doctor UI: machine facts labeled "not clinician verified" alongside raw wording
```

If NVIDIA fails, times out, or returns invalid schema:
- The raw patient answer remains safely persisted in PostgreSQL.
- Normalization records an explicit `unavailable` result with the specific failure reason (`timeout`, `network_error`, `authentication_failed`, `rate_limited`, `server_error`, `invalid_result`).
- The interview continues deterministically without silent fallback to mock.
- Offline development and CI remain default: `CLINICAL_NORMALIZATION_PROVIDER=mock` runs completely offline without an API key. See ADR-017 and [Phase 3B implementation status](phase3b-implementation-status.md).

## Stabilized Phase 4–6 boundaries

Staff HTTP routes require the existing active demo-doctor identity (`X-Demo-Doctor: true`, DEMO_MODE enabled outside production). Client-supplied reviewer/acknowledger names are rejected. This is a loopback synthetic demo boundary, not production login.

- POST `/triage/ws-ticket`: authenticated, returns a one-use ticket valid 30 seconds. Connect `/triage/ws` with subprotocols `["medikiosk", ticket]` and an allowed browser Origin; server selects `medikiosk`. Tickets do not go in URLs.
- GET `/triage/alerts`, `/triage/sessions/{id}/alerts`, `/sessions/{id}/alerts`: staff only. Items include `revision`, `trigger_active`, `acknowledgement_state`, source evidence and attribution. Status `resolved` can retain prior acknowledgement.
- POST `/triage/alerts/{id}/acknowledge`: `{expected_revision, note?}`. Actor comes from server identity; stale evidence/resolved alerts return 409; repeated acknowledgement preserves the first actor/time/note.
- Committed `alert_created`, `alert_updated`, `alert_resolved`, `alert_reactivated` events carry identifiers; authorized clients refresh authoritative records/counters. Acknowledgement events also prompt refresh. No human-delivery claim follows a transport write.
- POST `/sessions/{id}/documents`: multipart `file` and optional enum `document_type` (prescription/lab_report/other); active intake and document/sharing consent required. Actual content must decode; up to 10 MiB, 20 PDF pages, 20 million image pixels. Unsupported types/invalid content return 422 before persistence. Explicit fixture output has `mock_fixture` status and null confidence; arbitrary valid files have `unavailable` status and no extraction.
- GET document list/detail/file: staff only with sharing consent. Original previews use authenticated fetch and temporary browser object URLs. Public session detail excludes documents and staff alert payloads.
- POST extraction `/verify`: `{status, expected_status, expected_version, notes?}`. Server owns actor/time; each successful review increments `review_version` and preserves previous review metadata in audit. Confirmed/cancelled sessions and stale reviews return 409.
- Structured document data uses `observations` (typed lab rows) and `medications`. Missing lab flags are null, not Normal. Historical alias input is accepted by the schema; output uses observations.
- POST `/sessions/{id}/interview/speech/transcribe`: multipart audio, current `question_id`, optional mock fixture_id. Requires voice/sharing consent, active intake and current free-text eligibility before provider invocation. Multipart may already have spooled to disk; the UploadFile closes in finally. Successful response adds `candidate_token`; transcription does not save an answer.
- Adaptive answer with source voice requires `voice_candidate` signed token and exact candidate text, language, question, session and revision. Tokens expire after 10 minutes/restart. Editing uses source typed without a token. Confirmed provenance is audited in the answer transaction. Legacy answer endpoints only accept touch/typed.
- Speech provider invocation has a 15-second overall deadline. BHASHINI live ASR rejects unchecked native browser formats and requires validated 16-kHz mono PCM WAV. This is a conservative adapter boundary, not live format acceptance.


See the stabilization report for verification and remaining limits. Earlier conceptual diagrams describe planned scope where they exceed implemented boundaries.

## Implemented Phase 7 boundary

Phase 7 extends the modular monolith with three deterministic services behind the existing staff authorization dependency:

```text
typed document extraction
→ MedicalFactService (persisted medication/lab facts + source/review history)
├→ TimelineService (computed, deterministic, known/unknown date groups)
└→ DiscrepancyService (conservative explicit-evidence comparisons)
→ doctor evidence workspace
```

The timeline is computed from current source facts rather than materialized. The existing `timeline_fact` table is preserved as an unused compatibility scaffold; no producer writes to it. This avoids reconciliation/version drift and prevents upload timestamps from being presented as clinical dates.

Fact clinical fields remain immutable machine extraction. Clinician corrections are effective overlays stored in append-only `medical_fact_revisions`, with optimistic fact versions and server-owned reviewer identity. Rejected facts and facts from rejected source extractions are excluded from current timeline/discrepancy evaluation while remaining auditable.

Discrepancy IDs and timeline IDs are deterministic UUIDv5 values derived from stable source identifiers and comparison content. The engine does not call an LLM and does not infer diagnosis, adherence, treatment significance, dates, ranges, or normality. See [Phase 7 status](phase7-implementation-status.md).

## Implemented Phase 8 boundary

Phase 8 implements the clinician-controlled deterministic draft clinical summary workflow:

```text
Patient Interview + Normalization
+ Source-Linked Medical Facts (Medications & Labs)
+ Chronological Timeline
+ Conservative Discrepancies
+ Safety Screening Alerts
        ↓
Deterministic ClinicalSummaryService
(10 Fixed Structured Sections + Evidence Attribution)
        ↓
Immutable Machine Draft (generated_text, generated_structured_json)
        ↓
Doctor Working Review (reviewed_text, version tracking, revision notes)
        ↓
Append-Only Revision History (SummaryRevision records with ACTOR_TYPE)
        ↓
Confirmed Summary (confirmed_text, confirmed_by, confirmed_at, permanent lock)
```

Key architectural guarantees:
1. **Zero Hallucination / Strictly Deterministic**: No LLM or external generative model is used in summary synthesis. All statements derive directly and predictably from validated structured clinical facts.
2. **Fixed Ten-Section Structure**: Every generated draft conforms to:
   1. Patient Information
   2. Chief Complaint
   3. History of Present Illness
   4. Relevant Medical History
   5. Current Medications
   6. Investigations / Laboratory Findings
   7. Clinical Timeline
   8. Safety Alerts
   9. Potential Discrepancies
   10. Unknown / Not Reported Information
3. **Explicit Source Attribution (`EvidenceReference`)**: Every summary item retains provenance tracing back to its raw source (`patient_answer`, `normalized_fact`, `medical_fact`, `document`, `alert`, `discrepancy`, `timeline`).
4. **Separation of Stages**:
   - Machine Draft is immutable and never overwritten by manual edits.
   - Doctor Working Draft (`reviewed_text`) can be reviewed, edited, and iteratively saved.
   - Revisions are append-only in `summary_revisions` storing `actor_type` (`SYSTEM` vs `DOCTOR`), `actor_user_id`, `review_notes`, and structured/text snapshots.
   - Draft regeneration requires explicit replacement confirmation (`confirm_replacement=True`) if manual edits exist, preventing accidental data loss.
5. **Confirmation Locking**: Once confirmed, `confirmed_text` is saved with server-stamped `confirmed_by` and `confirmed_at`. The record is permanently locked against further edits or regeneration (HTTP 409 `CONFIRMED_IMMUTABLE`).
6. **Non-Diagnostic Boundary**: UI and backend never declare a diagnosis, prescribe treatments, or alter medication regimens. AYUSH pathways display explicit demonstration and supportive documentation disclaimers. See [Phase 8 status](phase8-implementation-status.md).

## Implemented Phase 9 boundary

Phase 9 hardens clinician-controlled verification, post-confirmation clinical amendments, session audit trails, and bidirectional cross-referencing:

```text
Doctor Workspace
├── Field-Level Verification (FieldVerificationService)
│   ├── Granular review of interview answers & summary statements
│   ├── Explicit states: unverified | verified | flagged
│   ├── Optimistic locking + append-only FieldVerificationRevision history
│   └── Automatic synchronization with interview_answers.verification_status
├── Confirmed Summary Clinical Amendments (IntakeService)
│   ├── Confirmed records remain strictly immutable (confirmed_text unchanged)
│   ├── Official versioned addendum: amended_text, amended_by, amended_at, amendment_notes
│   ├── Server-owned clinician identity (anti-forgery)
│   └── Preserved in audit history and summary revision log
├── Comprehensive Session Audit Trail (IntakeService)
│   ├── Chronological timeline of all patient, staff, and system events
│   ├── Captures actor_type, actor_user_id, action, entity_type, entity_id, metadata
│   └── Dynamic actor filtering (All, Doctor, Patient, System)
└── Bidirectional Cross-Referencing (CrossReferenceService)
    ├── Maps documents to linked structured medications, observations, and discrepancies
    ├── Traces summary statements back to source documents and extractions
    └── Provenance displayed directly in doctor DocumentViewer and SummaryWorkspace
```

Key architectural guarantees:
1. **Field-Level Provenance & Verification**: Doctors can independently verify or flag discrete patient-reported answers and summary statements without altering the patient's raw report. Each verification action increments version and generates an immutable revision entry.
2. **Confirmed Record Immutability with Versioned Amendments**: Once confirmed, a clinical summary is never modified in place. Subsequent clinical updates are filed as official amendments with mandatory clinician justification, preserving both the original confirmed text and the timestamped addendum.
3. **Server-Enforced Actor Provenance**: Client attempts to supply or forge `verified_by` or `amended_by` are rejected; identities are strictly resolved from authenticated session credentials.
4. **Complete Auditability**: Every intake, verification, summary revision, amendment, and triage alert generates an immutable `AuditLog` entry accessible via dedicated staff APIs. See [Phase 9 status](phase9-implementation-status.md).

