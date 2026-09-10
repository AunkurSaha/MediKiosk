# PHASE6 — Document storage and explicit mock extraction

Current report reconciled during stabilization on 2026-09-10. See [stabilization evidence and remaining gates](stabilization-implementation-status.md). This is a synthetic-data local prototype.

Uploads and local storage are implemented; real OCR is not. MIME declarations and actual file contents are validated before persistence. Only content-addressed synthetic PNG fixtures in ai/document_fixtures return mock extraction. Other valid files are stored with processing_status=unavailable and no fabricated facts/confidence.

The canonical structured key is observations; lab flags absent from the source remain null. API schemas validate structured fields and the doctor UI renders those rows beside an authenticated original-file preview. Historical mock output is labeled as potentially unrelated to the original upload; old raw rows are preserved.

Staff verification uses server identity, review_version conflict checks and append-only audit events retaining previous attribution/notes. Confirmed/cancelled records reject changes. Storage containment uses resolved paths and database failures trigger compensating file cleanup. Normal process failures are covered; a filesystem and SQL transaction cannot guarantee atomicity across abrupt power loss.

No new real OCR provider, OpenCV pipeline, cloud storage or timeline was introduced.

Final acceptance is governed by the stabilization matrix, not historical unit-test counts.
