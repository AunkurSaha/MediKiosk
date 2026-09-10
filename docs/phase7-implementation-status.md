# Phase 7 review and repairs — 2026-09-10

Phase 7 is a **partial backend foundation**, not a completed extraction/timeline/discrepancy feature. The user authorized review and repair of existing Phase 7 work after the earlier stabilization-only request. No new provider, database, clinical rule, or roadmap workflow was added.

## What was already present

- Medication, lab and timeline ORM models, an `extract_medical_facts` helper, and a hook in document upload.
- Migration `f27074ce1ef6` and merge `1dc135740d9c`, already applied to the local application database. The three fact tables were empty when inspected.
- Medication/lab facts derived from the existing typed document fixture parser. This is materialization of existing parsed fields, not a new AI extraction provider.
- A generic timeline table scaffold. There was no functioning timeline producer, API, ordering service, doctor timeline UI, discrepancy detection, or fact-level review API/UI. Those remain missing.

## Reproduced defects and repairs

| Finding | Reproduction | Repair / retained coverage |
|---|---|---|
| ORM mapper configuration breaks existing application paths | Existing document tests failed during setup: TimelineFact referenced a nonexistent DocumentExtraction relationship | Align timeline model to the already-applied generic timeline schema, remove the invalid relationship, remove duplicate session relationship and repair model exports. Mapper regression retained |
| Models and applied migrations describe different schemas | Alembic check wanted to add plural fact tables and remove singular tables; timeline columns differed entirely | Use deployed `medication_fact`, `lab_fact`, `timeline_fact` names and preserve all timeline scaffold columns. Forward migration `c83f627f4053` adds missing created_at indexes. No applied table/column was dropped or renamed |
| Local database password copied into tracked Alembic configuration | Focused check found a nonempty password in sqlalchemy.url | Replace with a password-free placeholder. Runtime Alembic already uses the existing environment-configured engine. Retained test fails safely without printing the credential |
| Retrying extraction duplicates facts | Focused test observed new row IDs on the second call | Lock persisted extraction, check existing materialization and leave existing rows/IDs unchanged on retry |
| Raw source omitted and debug logs print medical values | Original facts had null source_text; retry emitted medication names | Copy the complete original extraction text, retain the source extraction ID and leave unknown source locations null. Remove value logging; regression checks source and log contents |
| Unvalidated/partially created fact collections | Invalid medication name list was accepted without validation | Validate with existing StructuredDocument schema before creating any rows. Savepoint makes row insertion atomic; injected insertion failure leaves no partial facts and preserves original document/extraction with failed processing status |
| Unsupported timeline branch gives a false impression of implemented extraction | Branch expected clinical-note types and timeline_events that the current document schema cannot accept | Remove unreachable extraction branch. Keep the already-applied generic timeline table as an explicitly unused scaffold; do not invent events or dates |
| Ruff failures | Nine baseline errors including imports/model exports | Correct imports/exports and format touched Python files |

The helper also checks source document/session consistency, refuses locked sessions, skips rejected source extractions and retains unverified status. A document review does not establish a separate fact-level clinical verification workflow. No historical documents were automatically backfilled.

## Verification

- SQLite: **320 backend tests passed**.
- PostgreSQL: **320 backend tests passed** against the existing dedicated test database.
- Seven retained Phase 7 regressions in `backend/tests/test_phase7_repairs.py` cover mapper setup, credential-free config, idempotence/source/logging, collection validation, null lab flags, insertion failure isolation, and migration preservation/comparison.
- PostgreSQL migration verifier passed: prior phase/empty upgrades, downgrade/reupgrade in isolated schemas, application row fingerprints unchanged, and full Alembic/model comparison clean.
- SQLite migration regression preserves an existing generic timeline row through upgrade/downgrade/reupgrade and compares every Phase 7 table/column/FK/index. Historical Phase 1 SQLite users.email uniqueness representation differs from PostgreSQL; this test explicitly scopes comparison to Phase 7. Full SQLite migration parity is not claimed.
- Browser coverage in `frontend/e2e/phase7.spec.ts` uploads prescription and missing-flag lab fixtures, checks materialized rows and exact raw-source linkage directly in PostgreSQL via a read-only helper, renders the doctor document view, and rejects anonymous document reads.
- Full Playwright suite: **25 passed**, including both new Phase 7 persistence/browser journeys and existing Phase 1–6 regressions.
- Frontend component tests: **55 passed**. TypeScript/Vite build, ESLint, Prettier, Ruff (backend and new verification script), and Git whitespace checks passed.
- Configured-secret audit after removal: no matches across the scanned working tree/runtime logs/Git history. This is not proof of complete de-identification or all possible security defects.

## Remaining scope and limitations

The existing doctor UI displays document extraction JSON; it does not yet display a longitudinal timeline or dedicated fact review. No discrepancy engine or patient-versus-document comparison is implemented. Real OCR remains absent, and mock facts describe explicit fixtures, not arbitrary uploaded content. Source text is the whole extraction, not an invented exact page/span. Observation timestamps stay unknown when not established by the source.

The earlier full PostgreSQL process-restart acceptance remains unverified because Windows Application Control blocked pg_ctl.exe. Application services were restarted against the existing database for this review. An existing Git checkpoint was present at the start of this task; this does not establish that the prior restart gate was passed. No new commit is created by this review.
