# PHASE4A — Voice candidate and question playback

Current report reconciled during stabilization on 2026-09-10. See [stabilization evidence and remaining gates](stabilization-implementation-status.md). This is a synthetic-data local prototype.

The provider-neutral mock voice/TTS path remains implemented. Stabilization adds server-side voice consent at submission, signed candidate binding, current-question eligibility, source/provider audit linkage and cancellation handling. Edited candidates use typed provenance.

Multipart uploads can spool to temporary disk before service-level consent checks. The route closes the UploadFile in finally on success/rejection/failure. The application does not intentionally retain audio permanently. The earlier claims that audio never touched disk or that UI confirmation alone enforced provenance were incorrect.

Candidate tokens expire after 10 minutes and are invalidated by process restart. Unconfirmed candidates do not create answers. Confirmed provenance persists with the answer audit record. Mock audio is explicitly fixture behavior; it is not live speech recognition.

Final acceptance is governed by the stabilization matrix, not historical unit-test counts.
