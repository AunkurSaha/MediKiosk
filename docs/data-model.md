# Data Model — MediKiosk

This is the initial logical schema. Exact SQLAlchemy fields may evolve.

## 1. Principles

- UUID primary keys for externally referenced records.
- UTC timestamps.
- Explicit provenance.
- Separate AI/draft and clinician-confirmed state.
- Do not store large document binaries in PostgreSQL.
- Avoid JSON blobs for everything; use relational tables for durable searchable entities.
- JSON columns are acceptable for flexible structured subfields when justified.

## 2. Core entities

### users

Fields:
- `id`
- `name`
- `email` or username
- `password_hash` when password auth is introduced
- `role` — doctor / triage / admin
- `is_active`
- timestamps

Patient identity is not necessarily represented as a `users` login.

### patients

Fields:
- `id`
- `name`
- `demo_abha_id` nullable
- timestamps

For the prototype, collect only necessary identification.

### sessions

Fields:
- `id`
- `patient_id`
- `hospital_token`
- `language`
- `status`
- `started_at`
- `completed_at` nullable
- timestamps

Suggested status progression:
- `intake`
- `ready_for_review`
- `under_review`
- `confirmed`
- `cancelled`

### consents

Fields:
- `id`
- `session_id`
- `voice_processing`
- `document_processing`
- `share_with_doctor`
- `recorded_at`
- optional consent version

Do not reduce consent to one boolean.

### interview_answers

Fields:
- `id`
- `session_id`
- `question_id`
- `field`
- `value_json` or typed representation
- `raw_value`
- `source`
- `language`
- `confidence` nullable
- `verification_status`
- `created_at`

Suggested verification status:
- `patient_reported`
- `unverified`
- `clinician_verified`

### clinical_histories — phase 2+

Represents an assembled structured snapshot/version.

Fields:
- `id`
- `session_id`
- `version`
- structured sections;
- created time;
- source/revision metadata.

This may initially be computed from answers before a dedicated snapshot table is necessary.

### alerts — Phase 5 Implemented

Additive migration: `f54c306d1e24_red_flag_alerts.py`

Fields:
- `id` (String UUID primary key)
- `session_id` (String foreign key referencing `sessions.id` on delete CASCADE, indexed)
- `rule_id` (String, e.g. `RF-CHEST-001`)
- `rule_version` (String, e.g. `1.0.0`)
- `priority` (String: `emergency`, `urgent`, indexed)
- `category` (String: `cardiovascular`, `respiratory`, `infectious`, `neurological`, `gastrointestinal`)
- `reason` (String description of clinical concern)
- `triggering_facts_json` (JSON array of `TriggeringFact` records: field, value, raw_value, label)
- `status` (String: `new`, `acknowledged`, `resolved`, indexed)
- `acknowledged_at` (DateTime with timezone, nullable)
- `acknowledged_by` (String staff name / ID, nullable)
- `acknowledgement_note` (String optional action note, nullable)
- `created_at` (DateTime with timezone, indexed)
- `updated_at` (DateTime with timezone, nullable)

Constraints & Indexes:
- `uq_session_rule_alert`: Unique constraint on `(session_id, rule_id)` for idempotent evaluation and answer update reconciliation.
- Indexes on `session_id`, `status`, `priority`, `created_at`.

### documents — phase 6+

Fields:
- `id`
- `session_id`
- `object_key`
- `original_filename`
- `media_type`
- `document_type`
- `document_date` nullable
- `processing_status`
- `created_at`

### document_extractions — phase 6+

Fields:
- `id`
- `document_id`
- `extractor`
- `extractor_version`
- `raw_text` where appropriate
- `structured_json`
- `confidence`
- `verification_status`
- `created_at`

For richer provenance, individual extracted facts may become their own table.

### medications — phase 6/7+

Possible normalized fields:
- `id`
- `session_id`
- `name`
- `dose`
- `frequency`
- `source_type`
- `source_id`
- `confidence`
- `verification_status`
- date context

### observations — phase 6/7+

For lab/vital-like facts:
- `id`
- `session_id`
- `name`
- `value`
- `unit`
- `observed_at` nullable
- `source_type`
- `source_id`
- `confidence`
- `verification_status`

### discrepancies — phase 7+

Fields:
- `id`
- `session_id`
- `category`
- `patient_reported_json`
- `document_fact_json`
- `status`
- `resolution_note`
- timestamps

Do not automatically decide which source is true.

### clinical_summaries

Fields:
- `id`
- `session_id`
- `generated_text` nullable
- `generated_structured_json` nullable
- `reviewed_text` nullable
- `status`
- `generated_at` nullable
- `reviewed_by` nullable
- `reviewed_at` nullable
- `confirmed_by` nullable
- `confirmed_at` nullable
- `version`
- timestamps

Never overwrite `generated_text` with clinician edits.

### audit_logs

Fields:
- `id`
- `actor_user_id` nullable where system action
- `actor_type`
- `action`
- `entity_type`
- `entity_id`
- `metadata_json`
- `created_at`

Audit metadata should be minimal. Do not dump whole patient records into audit logs.

## 3. Relationship sketch

```text
Patient
  └── Session
      ├── Consent
      ├── InterviewAnswers
      ├── ClinicalHistory snapshots
      ├── Alerts
      ├── Documents
      │   └── DocumentExtractions
      ├── Medications
      ├── Observations
      ├── Discrepancies
      └── ClinicalSummaries

User
  ├── acknowledges Alerts
  ├── reviews/confirms Summaries
  └── creates AuditLog actions
```

## 4. Provenance model

Every clinically relevant fact should eventually answer:

- Where did this come from?
- Who/what extracted it?
- How confident was the extraction?
- Has a human verified it?
- When was it recorded?
- What original source can the doctor inspect?

## 5. Initial Phase 1 tables

Create first:
- users
- patients
- sessions
- consents
- interview_answers
- clinical_summaries
- audit_logs

Later migrations add the remaining entities.

## 6. Deletion/retention

Do not implement permanent patient-data deletion/retention policy by guesswork.

For the SIH prototype:
- provide clear kiosk session clearing;
- keep demo data controlled;
- document that production retention policy requires deployment/legal policy definition.

## Implemented Phase 2 persistence

Migration `d31a204b9e02` adds two tables without changing or deleting Phase 1 rows:

| Table | Durable fields / purpose |
|---|---|
| interview_runs | session_id PK/FK, flow_id, flow_version, immutable flow_snapshot JSON, cursor, revision |
| interview_requests | (session_id, request_id) composite PK; session FK to run; SHA-256 payload_hash for retry deduplication |

`interview_answers` remains append-only. New `value_json` values are envelopes such as `{"status":"answered","value":true}` or `{"status":"unknown","value":null}`. Legacy JSON strings are still read correctly. Raw wording, source, language, verification and timestamps remain separate columns. Corrections do not overwrite earlier records. Identical saves do not duplicate answer rows.

Applicability is derived from the pinned flow plus latest answers; there is no mutable is_active column to drift out of sync. Inactive branch rows stay historically available but are excluded from active answer/history responses and drafts. Reactivation reuses their latest fact IDs/timestamps. Current active answers are returned in configuration order, including after corrections.

`ClinicalHistory` is a Pydantic representation, not a new table. The completion snapshot is stored in the existing `clinical_summaries.generated_structured_json` column; doctor edits change only reviewed_text and review metadata. Original generated text/JSON and confirmation immutability are preserved.

### Finding local data

Connect a PostgreSQL client to host `127.0.0.1`, port `55432`, database `medikiosk`, schema `public`, user `medikiosk`. Use the password from your local ignored `backend/.env`; never copy it into source files. The database files themselves are under `C:\MEDIKIOSK\.runtime\pgdata`; inspect them through PostgreSQL, not as editable project files. The separate `medikiosk_test` database is only for automated tests.

```sql
SELECT s.id, s.hospital_token, s.language, s.status,
       r.flow_id, r.flow_version, r.cursor, r.revision
FROM sessions s LEFT JOIN interview_runs r ON r.session_id = s.id
ORDER BY s.created_at DESC;

-- All saved versions, including corrections and currently inactive answers:
SELECT question_id, field, value_json::jsonb, raw_value,
       source, language, verification_status, created_at
FROM interview_answers
WHERE session_id = 'replace-with-session-uuid'
ORDER BY created_at, id;

SELECT generated_text, generated_structured_json::jsonb,
       reviewed_text, status, version, confirmed_at
FROM clinical_summaries
WHERE session_id = 'replace-with-session-uuid';
```

Use `GET /api/sessions/{id}/interview` or the doctor detail to inspect **current active** history. A raw table query intentionally also shows inactive historical responses. The migration verifier uses isolated schemas inside medikiosk_test for empty/Phase 1 upgrades, then compares all existing app rows before/after its additive upgrade. No existing SQLite files are migrated or deleted.

## Implemented Phase 3A persistence

Additive migration `e43b205c0f13` creates `normalization_results`: id; session_id FK/index; unique source_answer_id FK; provider/provider_version; schema_version/policy_version; status; validated result_json; UTC created_at. The source answer ID itself identifies the immutable correction/version; no mutable answer_updated_at is needed.

One result snapshot per answer preserves successful, unrecognized, explicit unknown and provider-failure outcomes. Corrections create new answer/result IDs. Inactive source answers and their normalizations remain historical, excluded from active history. Reactivation reuses the original snapshot. Reads do not call a provider or backfill old records, including confirmed records.

Existing raw/typed answers, flow snapshots, retry receipts, generated summaries and review revisions are preserved. Normalization storage failure rolls back only its savepoint; source answers still save, and history reports an explicit unavailable/not_processed result. The pre-existing `generated_structured_json` completion snapshot now includes normalization alongside raw facts; deterministic generated prose is still based only on reported answers.

The competing NormalizedFact ORM from the other agent had no actual PostgreSQL table/migration and was removed from the active model registry. No persisted data was deleted. Empty, Phase 1, Phase 2 and actual app upgrades were verified with row fingerprints and Alembic comparison.

```sql
-- All normalization versions, including historical/inactive source answers:
SELECT n.id, n.source_answer_id, a.question_id, a.raw_value, a.language,
       n.status, n.provider, n.provider_version, n.created_at, n.result_json
FROM normalization_results n
JOIN interview_answers a ON a.id = n.source_answer_id
WHERE n.session_id = 'replace-with-session-uuid'
ORDER BY n.created_at, n.id;
```

Use the interview/history API to inspect active results. Table queries deliberately retain historical rows.

## Implemented Phase 3B persistence and Schema 1.1

Phase 3B reuses the existing `normalization_results` relational table without database schema alterations (Alembic head remains `e43b205c0f13`).

The `result_json` column stores the rich Schema 1.1 provenance envelope:
- `id`: unique result UUID.
- `source_answer_id`: foreign key to immutable interview answer.
- `source_question_id`, `canonical_field`, `original_language`, `original_text`: source context.
- `status`: `normalized` | `unrecognized` | `unknown` | `unavailable`.
- `reason`: failure or outcome reason code (`timeout`, `network_error`, `authentication_failed`, `server_error`, `rate_limited`, `invalid_result`, `no_match`, `explicit_unknown`).
- `provider`: `"nvidia"` (or `"mock"`).
- `provider_version`: `"1.0.0"`.
- `schema_version`: `"1.1"`.
- `model`: `"google/gemma-4-31b-it"`.
- `prompt_version`: `"nvidia-1.0"`.
- `latency_ms`: measured request latency in milliseconds.
- `token_usage`: prompt, completion, and total tokens when returned by the inference endpoint.
- `policy_version`: `"1.0"`.
- `created_at`: UTC ISO timestamp.
- `facts`: array of normalized facts, each carrying:
  - `normalized_concept`: canonical concept identifier.
  - `normalized_display`: authoritative clinical display label from catalog.
  - `normalized_value`: boolean/string/null depending on polarity and certainty.
  - `polarity`: explicit `"present"` or `"absent"`.
  - `evidence`: exact substring from patient source text.
  - `certainty`: `"certain"` or `"uncertain"`.
  - `confidence`: `None` (prohibits synthetic probabilities).
  - `verification_status`: `"machine_normalized"` or `"needs_verification"`.

No database schema migration is required between Phase 3A and Phase 3B because `result_json` safely encapsulates the additive model provenance attributes. Existing Phase 1, Phase 2, and Phase 3A records remain 100% intact across upgrades and process restarts.


## Stabilization schema and actual storage

Alembic head b72f516e3f42 adds non-null integer alerts.revision and document_extractions.review_version, default 0. Alert.created_at ORM nullability now agrees with its existing NOT NULL migration. Original source columns/rows are preserved; migrations and comparison are checked by verify-stabilization-migrations.py.

Documents and document_extractions exist in PostgreSQL. Files live under .runtime/uploads by default. structured_json.observations is the canonical lab array; missing flags are null. Review transitions retain prior status/actor/time/notes in audit_logs. Voice candidate tokens are signed, transient client-held values; confirmed candidate IDs/provider/model/source-answer linkage are in audit_logs. No audio table is added. Earlier plural conceptual entities are not exact table-name claims; the implemented Phase 7 tables are documented below.


## Implemented Phase 7 medical facts and review history

Schema head `d12f4a7b9c31` extends the repaired Phase 7 tables additively.

| Table | Purpose and important fields |
|---|---|
| `medication_fact` | Immutable extracted name, dosage, unit, route, frequency, duration, explicit start/end dates, instructions; session/extraction source links; raw text/location; verification state and optimistic `review_version` |
| `lab_fact` | Immutable extracted test/value/unit/reference range/source flag/explicit observation time; same provenance and review metadata |
| `medical_fact_revisions` | Append-only fact type/ID/version, original JSON, complete effective corrected JSON when present, review status, server reviewer FK, notes and timestamp; unique fact/type/version |
| `timeline_fact` | Preserved generic compatibility scaffold. Phase 7 does not populate or read it for the current timeline |

Current fact responses overlay the latest corrected JSON on immutable fact columns. Rejection changes workflow state but does not delete the source or revision history. Facts whose source extraction is rejected are excluded from current clinical views. No source page/region, date, flag, unit, range, or dose is synthesized when absent.

Timeline and discrepancy records are computed response objects, not database tables. Their deterministic IDs are reproducible from source IDs/content. This design keeps persisted structured facts as the source of truth and avoids duplicate timeline materialization.

## Implemented Phase 8 clinical summary schema

Schema head `1915850a59d1` adds additive fields to `clinical_summaries` and `summary_revisions` to support the multi-stage, doctor-controlled drafting and audit workflow:

| Table | Added / Enhanced Fields | Purpose |
|---|---|---|
| `clinical_summaries` | `confirmed_text` (Text, nullable) | Final clinician-confirmed text saved upon explicit sign-off; becomes permanently immutable. |
| `clinical_summaries` | `draft_provider` (String, default `'deterministic'`) | Identifies the generator engine (`'deterministic'`). |
| `clinical_summaries` | `draft_version` (Integer, default `1`) | Independent version counter for machine-draft generations. Increments on regeneration. |
| `summary_revisions` | `revision_type` (String, default `'edit'`) | Categorizes the lifecycle event: `'initial_draft'`, `'edit'`, `'regenerate'`, `'confirmed'`. |
| `summary_revisions` | `actor_type` (String, default `'DOCTOR'`) | Explicit provenance: `'SYSTEM'` for automated draft engine, `'DOCTOR'` for human clinician actions. |
| `summary_revisions` | `actor_user_id` (String, nullable) | Made nullable to accommodate system-initiated revisions where no user FK exists. |
| `summary_revisions` | `review_notes` (Text, nullable) | Clinician-entered notes explaining rationale for manual revisions or confirmation sign-off. |
| `summary_revisions` | `structured_snapshot` (JSON, nullable) | Structured fact/section snapshot recorded at the time of revision creation. |

All changes are strictly additive. Empty database migration, Phase 7 → Phase 8 upgrade, and downgrade/re-upgrade verification succeed cleanly.

## Implemented Phase 9 verification hardening schema

Schema head `7a3e8b1c4f92` adds additive amendment columns to `clinical_summaries` and introduces tables for granular field verification and revision history:

| Table | Added / Enhanced Fields | Purpose |
|---|---|---|
| `clinical_summaries` | `amended_text` (Text, nullable) | Preserves clinician-authored post-confirmation amendments and addenda without altering confirmed text. |
| `clinical_summaries` | `amended_by` (String, FK users.id, nullable) | Server-authenticated clinician ID who filed the official amendment. |
| `clinical_summaries` | `amended_at` (DateTime(timezone=True), nullable) | Timestamp of amendment sign-off. |
| `clinical_summaries` | `amendment_notes` (Text, nullable) | Required clinical justification for filing an amendment post-confirmation. |
| `field_verifications` | `id`, `session_id`, `field_type`, `field_id`, `status`, `verified_by`, `verified_at`, `notes`, `version`, `created_at`, `updated_at` | Granular field-level verification state (`unverified`, `verified`, `flagged`) with optimistic concurrency control and unique constraint on `(session_id, field_type, field_id)`. |
| `field_verification_revisions` | `id`, `verification_id`, `session_id`, `version`, `status`, `actor_user_id`, `notes`, `created_at` | Append-only revision trail for each field verification event, recording previous states and clinician provenance. |

All migrations are tested on PostgreSQL and SQLite, including forward upgrades, rollbacks, and schema re-application.

## Implemented Phase 10 FHIR R4 export architecture and mappings

Phase 10 adheres strictly to the non-negotiable architectural invariant: **internal relational schemas remain decoupled from FHIR**. No database migrations were required. Transformations are performed on demand by `FHIRAdapterService` into standard Pydantic v2 schemas:

### Entity-to-FHIR Resource Mapping

| Internal Model | FHIR R4 Resource | Standard Profile / Coding | Mapped Attributes & Invariants |
|---|---|---|---|
| `Patient` | `Patient` | `https://nrces.in/ndhm/fhir/r4/StructureDefinition/Patient` | `id: "patient-{id}"`, official identifiers for hospital token and demo ABHA ID (`https://healthid.ndhm.gov.in`), `name: [{text: name}]`, `gender: "unknown"` (or derived), `communication: [{language: bcp:47}]`. |
| `Session` | `Encounter` | NRCES Encounter Profile | `id: "encounter-{id}"`, `status: "finished"`, `class: AMB (ambulatory)`, `subject: Reference("urn:uuid:patient-{id}")`, `period: {start: created_at, end: completed_at}`. |
| `InterviewAnswer` | `QuestionnaireResponse` | HL7 Standard QuestionnaireResponse | `id: "qr-{id}"`, `status: "completed"`, `item: [{linkId: question_id, text: field_label, answer: [{valueString: raw_value}]}]`. |
| Chief Complaint / Intake | `Condition` | `https://nrces.in/ndhm/fhir/r4/StructureDefinition/Condition` | **Strict Non-Diagnostic Guardrail**: `clinicalStatus: "active"`, `verificationStatus: "provisional"`, `category: "problem-list-item"`. Note: `"Non-diagnostic. Requires clinical assessment."` |
| `MedicationFact` | `MedicationStatement` | `https://nrces.in/ndhm/fhir/r4/StructureDefinition/MedicationStatement` | `id: "med-{id}"`, `status: "active"` (or "stopped" if rejected), `medicationCodeableConcept: {text: name}`, `dosage: [{text: dosage + frequency}]`, `statusReason: [{text: verification_status}]`. |
| `LabFact` | `Observation` | `https://nrces.in/ndhm/fhir/r4/StructureDefinition/Observation` | `category: "laboratory"`, `code: {text: test_name}`, `valueString: "{value} {unit}"`, `interpretation: [{code: "H"/"L"/"N"}]`, `referenceRange: [{text: reference_range}]`, `status: "final"/"preliminary"/"cancelled"`. |
| `Document` | `DocumentReference` | LOINC `11488-4` Consultation note | `id: "doc-{id}"`, `content: [{attachment: {contentType: media_type, title: original_filename, size: file_size_bytes, hash: sha256_hash}}]`. |
| `ClinicalSummary` | `Composition` | LOINC `34105-7` Hospital Consultation note | `entry[0]` of Document Bundle. Includes structured sections linking to Chief Complaint, Questionnaire, Medications, Investigations, and Documents. Author is verified doctor (`Practitioner/{confirmed_by}`). |
| Multi-Resource Package | `Bundle` | `type: "document"` or `"collection"` | Uniform `urn:uuid:...` internal addressing with reference integrity validation producing standard `OperationOutcome`. |

## Implemented Phase 11 ABDM & HIS schema

Schema head `8b4e9c2d1f73` adds the `abdm_records` table to track ABDM National Health Stack integration state (M1, M2, M3) and Hospital Information System (HIS / EMR) dispatch status:

| Table | Field | Type | Constraints / Invariants | Description |
|---|---|---|---|---|
| `abdm_records` | `id` | String | Primary Key, UUID | Unique record identifier. |
| `abdm_records` | `session_id` | String | FK `sessions.id`, UNIQUE, INDEX | Bound to exactly one clinical intake session. Cascades on session deletion. |
| `abdm_records` | `patient_id` | String | FK `patients.id`, INDEX | Links to the patient entity. |
| `abdm_records` | `abha_number` | String(32) | Nullable | Standard 14-digit ABHA ID formatted as `XX-XXXX-XXXX-XXXX`. |
| `abdm_records` | `abha_address` | String(128) | Nullable | Patient ABHA PHR address (e.g. `patient@abdm` or `patient@sbx`). |
| `abdm_records` | `abha_status` | String(32) | Default `'unverified'`, INDEX | Verification state: `'unverified'`, `'verified'`, `'mock_verified'`. |
| `abdm_records` | `care_context_reference` | String(128) | Nullable | ABDM HIP Care Context reference (e.g. `medikiosk_ctx_<session_prefix>`). |
| `abdm_records` | `care_context_display` | String(256) | Nullable | Human-readable care context label (e.g. `MediKiosk OPD Intake - Token <token>`). |
| `abdm_records` | `care_context_status` | String(32) | Default `'unlinked'`, INDEX | ABDM M2 linking status: `'unlinked'`, `'linked'`. |
| `abdm_records` | `care_context_linked_at` | DateTime(tz=True) | Nullable | Timestamp when care context linking was confirmed. |
| `abdm_records` | `his_dispatch_status` | String(32) | Default `'not_dispatched'`, INDEX | Outbound HIS dispatch state: `'not_dispatched'`, `'pending'`, `'dispatched'`, `'failed'`. |
| `abdm_records` | `his_dispatch_receipt` | Text | Nullable | JSON-encoded receipt metadata containing `receipt_id`, `target_system`, `endpoint`, and timestamp. |
| `abdm_records` | `his_dispatched_at` | DateTime(tz=True) | Nullable | Timestamp of outbound transmission to hospital HIS gateway. |
| `abdm_records` | `consent_artefact_id` | String(128) | Nullable | ABDM consent artefact identifier for electronic record sharing. |
| `abdm_records` | `created_at` | DateTime(tz=True) | NOT NULL, server default | Record creation timestamp. |
| `abdm_records` | `updated_at` | DateTime(tz=True) | Nullable, onupdate | Record modification timestamp. |

The table is verified with zero model drift (`alembic check` clean) and full downgrade/upgrade migration coverage.


