# Document-aware minimum-necessary interview

Document-aware intake reuses the Clinical Evidence Graph and the pinned adaptive flow. It does not treat OCR as patient-reported truth and does not add a second clinical record.

For every applicable configured field, `GET /api/sessions/{session_id}/coverage` deterministically returns one of:

- `CONFIRMED`: addressed by a current patient answer, including explicit unknown/not-reported semantics;
- `DOCUMENT_SUPPORTED_UNCONFIRMED`: a safely mapped document fact exists but patient confirmation is still required;
- `CONFLICTED`: current patient history and document evidence disagree;
- `MISSING`: no sufficient evidence or patient answer exists;
- `NOT_APPLICABLE`: the pinned flow branch excludes the field.

Authority is ordered as current patient-confirmed answer, clinician-verified evidence, unverified document evidence, machine-normalized suggestion, then missing. A conflict remains visible even when a higher-authority source controls current history; software does not decide which source is clinically true.

The initial safe mapping is deliberately narrow: `MEDICATION_MENTION` document evidence maps to the configured medication-history fields. Laboratory observations remain document evidence and timeline material; they do not satisfy an interview field and patients are not asked to interpret them. No diagnosis/problem mapping is inferred from a medicine or lab result.

Before the generic medication turn, an unconfirmed medication fact produces one `DOCUMENT_CONFIRMATION` question naming only the extracted medicine details. Yes/no/not-sure are explicit patient actions. A “yes” creates new patient-answer rows for the canonical medication fields and new patient evidence linked to the original evidence/document/fact IDs. The original document evidence remains unchanged. A rejection is also stored separately, leaves the document fact intact, and allows the existing discrepancy service to report the disagreement. Answered confirmation evidence is not asked again.

Completion remains controlled by the existing deterministic adaptive engine. Unconfirmed document evidence is never inserted into flow answers, so it cannot complete a required history field. Red-flag rules and emergency routing are unchanged.

The doctor workspace displays coverage counts, field state, extracted display value, document filename/page when available, and verification state. Patient copy avoids evidence-graph, RAG, and retrieval terminology.

The synthetic acceptance scenario uses separate prescription and laboratory evidence: Metformin 500 mg twice daily is confirmed through dialogue, while fasting glucose 146 mg/dL remains document evidence and is never presented for patient interpretation. Question-reduction metrics must be calculated by an executed deterministic run and are not hard-coded.
