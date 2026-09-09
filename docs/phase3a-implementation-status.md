# Phase 3A verification and implementation report — 2026-09-09

## Review of the previous completion claim

The supplied summary overstated completion. Inspection found a working integration skeleton but material gaps:

- The local app database was still at Phase 2 revision d31a204b9e02. The claimed normalized_facts table did not exist in PostgreSQL, and its ORM model had no corresponding migration.
- Two competing provider/model implementations existed. The active service bypassed the strict ProviderResult contract, ignored timeout, and unconditionally selected the mock.
- Every question was treated as eligible, including typed answers; explicit unknown states were not respected by the persistence path.
- Only recognized successful facts were stored. Missing/failure results lost durable status, identifiers and timestamps in the API representation.
- A caught INSERT failure could leave the surrounding SQLAlchemy transaction failed, despite the comment saying intake would continue. Provider exceptions were included in logs.
- The mock contained corrupted Bengali entries and an uncalibrated 0.95 confidence for every match.
- The 76 existing tests were Phase 1/2 regressions, not dedicated Phase 3A coverage. Comprehensive edge-case, browser, migration and restart acceptance evidence was missing.
- The summary's red-flag statement was misleading: no red-flag engine is implemented in this phase.

These gaps have been corrected. No existing patient/answer/summary records were deleted.

## 1. Implemented behavior

Eligible free-text answers now produce optional, validated, durable normalization with original wording/provenance preserved. Typed responses bypass the provider. The interview continues on unavailable, invalid, unsupported or timed-out normalization. Doctor history shows reported and machine representations separately. Existing Phase 1/2 workflows remain operational.

## 2. Architecture

normalization_policy → provider-neutral normalization service → bounded async provider invocation → strict output validation → trusted concept catalog → immutable result snapshot. The adaptive/intake services invoke persistence after the source answer is flushed. A savepoint isolates normalization writes/reads from the raw-answer transaction. InterviewEngine itself remains unchanged: normalization never controls next question, conditions, required fields, consent or completion.

## 3. Schemas

ProviderInput contains text, language, canonical field and minimal flow/question context. ProviderResult schema 1.0 permits only normalized/unrecognized/unknown status and up to five unique allowed concepts, exact source evidence, certainty and confidence. Unexpected keys, diagnoses, source-field/language mismatches, absent evidence and invalid confidence fail closed.

Normalization attaches server-owned immutable answer/question/field linkage, original text/language, result ID, status/reason, provider/version, schema/policy versions and UTC created_at. Each NormalizedFact has canonical concept, trusted display/value, evidence, nullable confidence, certainty and machine_normalized/needs_verification status. Neither status is clinician verification.

## 4. Provider interface

ClinicalNormalizationProvider is an async Protocol with stable name/version and normalize(ProviderInput) returning an untrusted JSON-compatible dictionary. The service enforces a timeout; adapters must use nonblocking I/O and honor cancellation. Default mock needs no credentials; disabled gives an explicit unavailable state. Invalid provider names/configuration fail startup. No SDK, external call or automatic external fallback exists.

## 5. Vocabulary and languages

45 explicit fixtures cover thirteen concepts in English/Bengali/Hindi plus uncertain and unknown phrases: CHEST_PAIN, ABDOMINAL_PAIN, HEADACHE, FEVER, COUGH, DYSPNEA, NAUSEA, VOMITING, SWEATING, DIZZINESS and pressure-like/sharp/burning pain descriptions. Lookup alone folds case/whitespace and NFC; original text remains untouched.

There is no fuzzy/substring inference or general translation. Negated/contextual/combined or unsupported phrases remain unrecognized. Mock confidence is null; uncertain fixtures remain needs_verification. Wording/translation accuracy is prototype/unvalidated.

## 6. Persistence and migrations

Migration e43b205c0f13 adds normalization_results with a unique source_answer_id, session linkage, provider/version, schema/policy version, status, validated result JSON and timestamp. One snapshot belongs to one immutable answer version. The unused, unmigrated NormalizedFact ORM and competing provider files were removed after confirming no such table existed in the local app database.

Successful, unknown, unrecognized and provider-failure outcomes are stored. If enrichment storage fails, the answer still persists and the API reports normalization unavailable/not_processed. No automatic reprocessing/backfill is performed on GET, replay, navigation, completion or confirmation.

Migration verification passed for empty schema, Phase 1 → latest, Phase 2 → latest and the actual app DB, followed by Alembic comparison. Every pre-existing table's row counts and SHA-256 fingerprints stayed unchanged, including sessions, answer history, summaries, review revisions, flow snapshots and request receipts. The app had 6 sessions, 54 answers and 5 summaries at that comparison; browser checks subsequently added synthetic records.

## 7. Active and historical behavior

Source correction creates a new answer ID and a new normalization. Only the latest active source's result is exposed. Earlier results remain stored. Branch deactivation hides both reported/normalized facts; reactivation reuses the exact saved result ID/timestamp/provenance. Retried saves do not duplicate or recompute results. Provider/fixture changes apply to new answer versions, not historical snapshots.

## 8. Structured history

The additive Fact.normalization property coexists with unchanged value/raw_value/source/language/verification fields. It is null for ineligible typed/AYUSH fields, explicit unavailable for eligible historical answers with no result, or a typed result snapshot. Active-history filtering applies to both representations. The deterministic prose draft continues to use reported facts only; the structured completion snapshot includes normalization. Generated prose never becomes canonical.

## 9. Doctor UI

Original patient wording remains in its source language. Neutral-colored normalization panels show canonical display, reported certainty, machine/needs-verification label, and expandable source/provider metadata. Unavailable/unknown states remain visible. Machine data is always labeled not clinician verified, including after summary confirmation. The existing review editor and immutable confirmation behavior are preserved.

## 10. API

No new public endpoint. Existing interview state/history and session/doctor detail include Fact.normalization. Source-answer create payloads, consent, flow selection, cursor/revision and summary review/confirm contracts remain unchanged. /api/config reports phase 3A without secrets.

## 11. Verification results

| Check | Result |
|---|---|
| SQLite backend suite | 159 passed: 76 existing + 83 normalization tests |
| PostgreSQL backend suite | 159 passed |
| Frontend component suite | 33 passed: 27 existing + 6 doctor normalization tests |
| Chromium E2E | 7 passed, including Bengali normalization/edit/unavailable/confirmation |
| Real application and PostgreSQL restart | Passed; saved results, interview progress and confirmations unchanged |
| Browser resume checks after restart | 2 passed |
| TypeScript / production build | Passed |
| ESLint | Passed, zero warnings |
| Prettier | Passed |
| Ruff | Passed |
| Empty, Phase 1, Phase 2 and real app upgrades | Passed; pre-existing data preserved |
| Alembic schema comparison | No new upgrade operations detected |

Restart evidence and final acceptance are recorded in [implementation-status.md](implementation-status.md). Artifacts are under ignored .runtime. The backend has one existing Starlette/AnyIO deprecation warning per run; Playwright prints a console-color environment warning. Neither indicates a failed test. Remote CI was not run.

## 12. Limits

This is exact fixture-based symptom/qualitative normalization, not clinical validation, broad NLP, full translation, diagnosis, medication extraction or treatment. Many eligible medication/allergy/history phrases intentionally remain unrecognized. Context stays attached via canonical field; downstream code must not flatten a family/allergy context into a current symptom.

The timeout contract is cooperative: future adapters must honor async cancellation and use transport timeouts. Results are not automatically retried/reprocessed; a later explicit, audited reprocessing design is needed if that behavior is desired. Old confirmed records are not backfilled or rewritten.

No real provider, credentials, automatic complaint switching, voice, OCR, documents, red flags, triage engine, WebSockets, timeline, AI summary, FHIR, ABDM, production auth or Docker changes were introduced.

## 13. Files

- Backend: schemas/normalization.py; models/normalization.py; services/normalization.py, normalization_provider.py, normalization_policy.py; schemas/adaptive.py; services/adaptive.py and intake.py; models/__init__.py; main.py; .env.example.
- Migration: alembic/versions/e43b205c0f13_normalization_results.py.
- Fixtures/contract: ai/normalization/mock_vocabulary.json and README; ai/ontology/normalization_concepts.json; ai/prompts/clinical_normalization_v1.md.
- Frontend: api/interview.ts; components/doctor/NormalizationPanel.tsx; i18n/normalization.ts; routes/doctor/index.tsx; index.css.
- Tests: backend/tests/test_normalization.py; frontend/src/test/normalization.test.tsx; frontend/e2e/normalization.spec.ts and restart.spec.ts.
- Operations: scripts/verify-phase3a-migrations.py; extended scripts/verify-restart.ps1; root .env.example.
- Documentation: corrected PHASE_3A_SUMMARY.md, README and architecture/data/API/clinical/testing/roadmap/traceability/prompting/memory/decision/status docs.
- Removed conflicting unused files: backend/app/services/provider.py, mock_provider.py and models/normalized_fact.py. No database table or existing clinical rows were removed.

## 14. Recommended Phase 3B task

Add one explicitly selected real normalization provider behind the existing interface, disabled by default, after agreeing on provider and data-handling requirements. Evaluate schema compliance, evidence, negation, context and uncertainty against multilingual fixtures; enforce transport/service timeouts, output allowlist and deterministic fallback. Keep raw wording and all source/result versions. Ask for credentials only after that provider decision. Complaint candidates remain suggestions requiring explicit confirmation; do not enable automatic flow switching or later roadmap features.
