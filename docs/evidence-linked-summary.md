# Evidence-linked clinical summary

The doctor workspace uses the existing deterministic clinical-summary lifecycle: a stored system draft, clinician working text, append-only revisions, and an immutable confirmed record. It does not create a parallel summary or use an LLM to explain provenance.

Each structured statement carries a stable statement ID, source record IDs, a plain verification state, a source badge, and deterministic “Why is this here?” lines. Supported explanations cover patient reports, normalized suggestions, document extraction, patient confirmation of document content, clinician verification, deterministic safety rules, discrepancies, and timeline evidence. Document links preserve the document/fact/extraction IDs, filename, page and bounding box when available, OCR provider/model, original extracted value, and verification state. Missing metadata remains null; no confidence percentage is invented.

Coverage is snapshotted into each generated draft. The doctor response shows confirmed, document-supported but unconfirmed, conflicted, and missing totals, so unresolved history is not presented as complete. Doctor prose edits do not replace the structured evidence snapshot. A clinician field verification is appended and displayed without relabelling normalization or OCR as inherently verified.

Summary GETs deserialize the persisted `generated_structured_json`; they do not regenerate it. Confirmation therefore freezes the generated evidence/coverage snapshot and the confirmed prose. Later amendments remain separate versioned records under the existing amendment workflow.

The same doctor-authorized summary response includes a read-only pre-arrival packet contract assembled from existing visit, facility, selected-doctor, queue, routing, history, document, alert, coverage, and summary data. `packet_reference` is an opaque `mkp:<session UUID>` reference containing no patient name or clinical content. QR rendering is deferred to avoid a new dependency; a future QR may encode only that opaque reference or a protected local URL.

Source navigation uses the existing doctor document area through a document anchor. Page and bounding-box metadata are exposed when present; Phase 7 does not add PDF annotation infrastructure.
