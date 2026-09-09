# Engineering and Domain Rules — MediKiosk

These rules are mandatory unless explicitly superseded by an ADR in `decisions.md`.

## A. Product rules

1. MediKiosk assists **pre-consultation intake**, not autonomous diagnosis.
2. Doctor is final reviewer for the clinical record.
3. Patient-reported, document-extracted, AI-inferred, and doctor-verified data must be distinguishable.
4. Unknown data remains unknown; do not fabricate defaults.
5. Red flags prompt clinical assessment; they do not assert a diagnosis.
6. Low-confidence OCR/ASR/LLM results require verification or fallback.
7. Original/source data must remain traceable.

## B. Architecture rules

1. Keep MVP as modular monolith.
2. Frontend: React/Vite/TypeScript.
3. Backend: FastAPI/Python.
4. DB: PostgreSQL.
5. Use Alembic migrations.
6. Use typed Pydantic API schemas.
7. Keep external providers behind interfaces/adapters.
8. Do not add Redis until a real need exists.
9. Do not introduce microservices without an ADR.
10. FHIR is an export/integration boundary, not the internal database model.

## C. AI rules

1. Never parse model output with fragile free-form assumptions when a schema can be enforced.
2. Require structured output for extraction/normalization whenever possible.
3. Validate all AI output using Pydantic.
4. Never give a raw model response directly the status of a verified clinical fact.
5. Store model/provider/version metadata for clinically relevant derived outputs once AI integration begins.
6. Never use an LLM as the sole red-flag engine.
7. Never use LLM output to bypass required consent.
8. Summary prompts must say:
   - do not diagnose;
   - do not invent;
   - use only provided structured facts;
   - represent missing information as unknown/not reported.

## D. Interview rules

1. Interview flow is driven by configuration + deterministic state.
2. Support five initial complaint families only when Phase 2 is reached:
   - chest pain;
   - abdominal pain;
   - fever;
   - headache;
   - cough/breathlessness.
3. Core history sections:
   - chief complaint;
   - HPI;
   - past medical history;
   - past surgical history;
   - current medications;
   - allergies;
   - family history;
   - personal history;
   - review of systems.
4. Do not ask every possible question to every patient.
5. Persist answers incrementally.

## E. Safety-rule rules

1. Store rules as version-controlled YAML/JSON/Python configuration.
2. Every fired rule must have stable `rule_id`.
3. Store trigger facts.
4. Prefer deterministic boolean/threshold logic.
5. Clinical rule content must be treated as prototype/demo logic unless clinically reviewed.
6. Tests must cover each rule's positive and negative path.

## F. Data rules

1. Use UUIDs or similarly non-sequential public identifiers for sessions.
2. Store timestamps in UTC; localize only for display.
3. Never mutate confirmed clinical history without creating a new version/audit event when versioning is implemented.
4. Preserve generated summary and clinician-confirmed summary separately.
5. Document files live in object storage; database stores metadata/references.
6. Never store raw binary document content in ordinary relational columns.
7. Keep provenance metadata with extracted facts.

## G. API rules

1. Prefix API routes with `/api`.
2. Use consistent error envelope.
3. Validate all input.
4. Do not leak stack traces.
5. Use HTTP status codes semantically.
6. Mutations should return the resulting canonical resource or a clear result object.
7. Contracts changed in code must be reflected in `api-contract.md`.

Suggested error envelope:

```json
{
  "error": {
    "code": "CONSENT_REQUIRED",
    "message": "Consent is required before starting the interview.",
    "details": null
  }
}
```

## H. Frontend rules

1. No backend/provider secrets in frontend environment variables.
2. UI strings belong in localization resources.
3. Every remote request needs loading/error handling.
4. Never infer a successful save before backend confirms it.
5. Prefer simple accessible native semantics over complex custom controls.
6. Patient screens should avoid dense tables.

## I. Security rules

1. No secrets committed.
2. Passwords hashed with a strong password hashing algorithm.
3. Role checks enforced server-side.
4. Authorization is not a frontend concern alone.
5. Avoid logging raw patient answers/documents by default.
6. Audit logs must not become a second uncontrolled copy of all patient data.
7. Production-like data must never be added to fixtures.

## J. Git/code rules

1. Small focused commits.
2. Do not commit build output, virtualenvs, `.env`, node_modules, local DBs, OCR caches, or uploaded patient documents.
3. Add tests with behavior changes.
4. Do not perform broad rewrites when a focused change is enough.
5. Prefer boring readable code over clever abstractions.
6. Comments should explain *why*, not restate obvious code.
