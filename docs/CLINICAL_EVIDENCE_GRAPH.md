# Clinical Evidence Graph

## Purpose and safety boundary

The Clinical Evidence Graph is MediKiosk's persistent, provenance-first aggregation layer. It
does not replace the source answer, normalization, document fact, alert, discrepancy, summary,
FHIR, or ABDM tables. Each node says what a source asserted and how it was handled; it does not
claim one absolute clinical truth.

Only versioned deterministic red-flag rules may produce emergency or urgent safety outcomes.
LLM/RAG output, normalization, and OCR are evidence inputs and cannot decide emergency state,
override a rule, diagnose, prescribe, or become verified facts automatically. There is no
`NO_DOCTOR_REQUIRED` routing state.

## Data model

`clinical_evidence` stores:

- patient and encounter (`session_id`) ownership;
- optional normalized `concept_code` and JSON-safe value;
- immutable source identity (`source_type`, `source_id`, `stable_key`);
- original, translated, and normalized text as distinct fields;
- language and nullable confidence;
- verification status and the latest clinician attribution/reason;
- source-specific JSON metadata; and
- creation/update timestamps.

`clinical_evidence_conflicts` links two retained evidence nodes with a reason and clinician
attribution. A conflict never deletes or overwrites either source.

The migration backfills existing interview answers, normalization facts, typed medication/lab
facts, and deterministic alerts. Existing canonical tables remain intact.

## Source types

- `PATIENT_TEXT`
- `PATIENT_VOICE`
- `DOCUMENT`
- `PREVIOUS_ENCOUNTER`
- `CLINICIAN`
- `DETERMINISTIC_RULE`
- `EXTERNAL_RECORD`

## Verification lifecycle

- `UNVERIFIED`: mandatory initial state for OCR/document-derived evidence.
- `PATIENT_CONFIRMED`: a patient has explicitly submitted/confirmed the answer, including a
  confirmed ASR candidate.
- `CLINICIAN_VERIFIED`: a doctor reviewed and accepted the evidence.
- `REJECTED`: retained for audit but excluded from trusted use.
- `CONFLICTING`: explicitly linked evidence disagrees and remains available for review.

Only doctors authorized for the encounter may verify, reject, or mark conflicts. Each transition
adds an `AuditLog` containing actor, timestamp, evidence ID, old/new state, and optional reason.

## Provenance and idempotency

Source identity is deterministic: `(source_type, source_id, stable_key)` is unique. Raw answers use
`raw_answer`; normalized projections use `normalized:<concept>`; document entities use their entity
type; deterministic alerts use `rule_result`. Reprocessing a persisted source therefore returns the
existing node instead of duplicating it. `concept_code` remains nullable for raw answers when no
approved normalization exists.

Patient voice metadata may retain ASR candidate/provider/model while original and translated text
remain separate. Document metadata retains document/extraction IDs, entity type, source location,
OCR provider/version, and nullable OCR confidence. Rule metadata retains rule ID/version, reason,
category, alert state, and triggering evidence IDs.

## Integrations

Patient answers dual-write a patient-confirmed raw evidence node. Eligible normalization results
add concept projections without altering the original. The active document pipeline creates
unverified evidence for each typed medication or laboratory fact; clinician medical-fact review
synchronizes its evidence state. The deterministic red-flag engine creates an explainable rule
result node and leaves WebSocket alert behavior unchanged.

Existing computed discrepancies remain the conservative comparison engine. The conflict table is
the durable relationship layer for reviewed discrepancies and supports answering which retained
evidence items support a conflict.

`get_previous_verified_evidence` returns only `PATIENT_CONFIRMED` and `CLINICIAN_VERIFIED` nodes
from other encounters. Unverified document/OCR evidence is excluded. `get_verified_context`
separates clinician-verified, patient-confirmed, unverified-document, deterministic-rule, and
conflicting evidence for future summary consumers; the current summary engine is unchanged.

## Authorization and API

Authenticated patients can read only evidence belonging to their own sessions/patient context.
Doctors use the existing assignment, hospital-membership, and consent checks. Triage staff cannot
read full encounter evidence or perform doctor-only state changes.

Read endpoints:

- `GET /api/evidence/encounters/{session_id}`
- `GET /api/evidence/encounters/{session_id}/context`
- `GET /api/evidence/patients/{patient_id}`
- `GET /api/evidence/{evidence_id}`

Doctor-only transitions:

- `POST /api/evidence/doctor/encounters/{session_id}/{evidence_id}/verify`
- `POST /api/evidence/doctor/encounters/{session_id}/{evidence_id}/reject`
- `POST /api/evidence/doctor/encounters/{session_id}/{evidence_id}/conflicts`

## Future consumers

This foundation is designed for later Rapid Safety Screen, MediRoute, Doctor Matching,
Document-to-Dialogue, Minimum-Necessary Interview, Clinical Coverage, Evidence-Linked Summary,
“Why is this here?”, and Pre-Arrival Clinical Packet work. None of those later features is
implemented by this phase. Confirmed/verified nodes are shaped for later FHIR projection, but the
current FHIR and ABDM architectures remain unchanged.
