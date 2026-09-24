# Patient Evidence RAG

## Boundary

Patient Evidence RAG is a clinician-only search index over canonical MediKiosk records. It is not
a chatbot, clinical workflow authority, diagnosis engine, or second clinical database. Canonical
interview answers, `ClinicalEvidence`, extracted medical facts, document extractions, and clinical
summaries remain authoritative. A failed index operation never rolls back those records.

The existing `knowledge_chunks` corpus remains a logically and physically separate curated
knowledge RAG used by adaptive interview support. Patient records are stored only in
`rag_patient_chunks`; knowledge and patient embeddings are never searched together.

## Canonical projection and chunk identity

`app.services.patient_rag.build_patient_chunks` produces clinically meaningful records rather than
fixed-width character slices:

- one interview-answer chunk per answer;
- one evidence chunk per append-oriented `ClinicalEvidence` record;
- one paragraph chunk per document extraction;
- one structured medication or laboratory chunk per extracted fact;
- one versioned chunk per clinical summary.

Each chunk preserves its canonical source ID, patient/session/document IDs, document filename and
page when available, extraction provider/confidence, verification status, event timestamp,
current/historical state, conflict state, and metadata. The logical chunk identity is
`(source_type, source_record_id, chunk_key)`; provider/model/version representations of that same
chunk do not create additional canonical chunks. Checksums and embedding identity fields allow
changed or incompatible representations to be identified independently.

## Embedding coverage and readiness

`app.services.patient_rag_coverage.get_patient_embedding_coverage` compares the current canonical
projection with one exact provider/model/version/dimension identity. Each canonical chunk is
classified once as indexed, pending, failed, missing, or stale. Indexed coverage requires a
current checksum and a present, finite vector of the requested dimension. Orphaned representation
rows are retained but ignored, and every representation query includes `patient_id`.

Coverage is `100 * indexed / canonical`, or `0.0` when no canonical chunks exist. A provider is
ready for patient search only when at least one canonical chunk exists and every canonical chunk
is currently indexed, with no pending, failed, missing, or stale chunks. This check reports
readiness only; it never changes the active search provider.

## Single-patient provider backfill

`app.services.patient_rag.backfill_patient_embeddings` fills one explicitly supplied provider
identity for one patient. It reuses current canonical chunks and exact representation rows,
retries failed or pending rows, refreshes stale checksums, creates missing representations, and
never modifies another provider's rows. Work is bounded by `RAG_EMBEDDING_BATCH_SIZE` (default
`16`). Provider vectors are accepted individually only when non-empty, finite, and exactly the
provider's declared dimension. A batch exception or mismatched result count leaves every affected
row failed with no searchable embedding; an invalid vector fails only its row while valid peers in
the same batch may be indexed.

Dry-run mode is strictly read-only: it makes no embedding call and performs no insert, update,
delete, flush, commit, or status transition. It reports current coverage, classification counts,
prospective work, and estimated batches. Backfill and dry-run report readiness but never activate
the provider for search.

## Retrieval and ranking

PostgreSQL retrieval applies `patient_id` and optional source, verification, document, and date
filters in SQL before nearest-neighbour ordering. The configured 2048-dimensional production model
uses the pgvector HNSW half-vector expression index. Exact lexical candidates are collected through
the same patient-scoped query and hybrid-ranked so medicine names, doses, units, abbreviations, and
lab values are retained. SQLite E2E uses the same persisted schema with deterministic lexical
feature-hash vectors and in-process cosine scoring after a patient-scoped SQL query.

The deterministic score is:

```text
0.50 * non-negative cosine similarity
+ 0.30 * query-token overlap
+ 0.12 * intent match
+ verification/current/conflict boosts
```

Clinician-verified evidence receives `+0.20`, patient-confirmed `+0.18`, patient-reported `+0.10`,
current evidence `+0.08` except for history requests, and conflicted evidence `+0.12` for explicit
conflict searches. Historical and conflicting records remain retrievable; they are not deleted or
silently resolved.

## Safe response generation

Responses are rendered deterministically from retrieved structured evidence. No generation model
or general medical knowledge is used. The API returns answer text and separate evidence objects.
When support is absent, the exact answer is:

> No supporting patient evidence was found.

Document-only medications are explicitly described as unverified with current use not confirmed.
Patient- or clinician-confirmed evidence is labelled accordingly. Conflicts are surfaced for
clinical review without resolving them or inferring a diagnosis.

## Authorization and lifecycle

The doctor endpoints use the existing assigned-doctor/session dependency, including facility and
assignment checks. Patient and triage identities cannot use these endpoints. The requested session
determines `patient_id`; the client cannot supply or override it.

Search performs an idempotent refresh first, so persisted confirmations and reviews are visible
without making intake depend on an embedding provider. Explicit reindex and status endpoints are
available to authorized doctors. Operators can run:

```text
python -m app.scripts.reindex_rag --patient PATIENT_ID
python -m app.scripts.reindex_rag --session SESSION_ID
python -m app.scripts.reindex_rag --document DOCUMENT_ID
python -m app.scripts.reindex_rag --all --confirm-all
python -m app.scripts.reindex_rag --provider nvidia --patient-id PATIENT_ID --dry-run
python -m app.scripts.reindex_rag --provider nvidia --patient-id PATIENT_ID
```

NVIDIA provider mode requires an explicit patient ID. NVIDIA bulk execution is disabled even when
bulk confirmation flags are supplied.

Provider errors leave chunks in `failed` state with a bounded reason. A later search or explicit
reindex retries them. The `--all` operation requires explicit confirmation.
