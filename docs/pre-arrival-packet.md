# Secure pre-arrival packet

Phase 8 persists an immutable, versioned snapshot of the already-completed intake for secure clinician handoff. It does not add clinical interpretation or change routing, matching, queue, coverage, evidence, or summary semantics.

The owning patient creates or reuses the packet at `POST /api/sessions/{session_id}/packet`. Creation requires a completed intake with a selected facility and doctor. The stored snapshot contains the existing visit, routing, structured history, document extraction provenance, timeline, red flags with rule evidence, coverage, evidence-linked clinical summary, and conflicts. Queue status is read live and is not rewritten into the immutable clinical snapshot.

`POST /api/sessions/{session_id}/packet/handoff-token` returns a newly generated opaque token once. Only its SHA-256 hash is persisted. Issuing another token rotates the credential and immediately invalidates the former URL. The QR encodes only `/handoff/p/{opaque-token}`; it contains no patient or clinical data. Packets expire after `PACKET_EXPIRY_MINUTES` (default 1440), while handoff credentials expire after `HANDOFF_TOKEN_EXPIRY_MINUTES` (default 60).

Anonymous resolution returns only `AUTH_REQUIRED`. Clinical content is released only to the doctor assigned to that visit with active facility membership. Triage staff, other doctors, and cross-patient access are forbidden. Patient revocation is immediate. Creation, token issuance/rotation, doctor viewing, and revocation are audited without recording the raw token or clinical values.

The historical `mkp:<session UUID>` packet reference remains inside the structured snapshot for compatibility. It is not accepted as a handoff credential and must never be encoded in a QR.

This synthetic prototype uses a localhost handoff URL. It has no production deep-link domain, external hospital federation, offline medical record in the QR, production mobile-scanner validation, packet amendment workflow, or production consent delegation. A revoked or expired packet is retained for audit; re-creation of the same version does not silently refresh it.
