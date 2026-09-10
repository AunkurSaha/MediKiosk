# Security and privacy — synthetic local prototype

No production security, clinical validation or regulatory compliance is claimed. Use synthetic data and loopback interfaces. The existing demo identity requires a server-side active doctor record and explicit DEMO_MODE outside production. Header-based demo access is not production authentication. Original Phase 1 patient routes retain UUID-based access; real patient authentication and access tokens remain required before external deployment.

Staff document reads/reviews, triage data and acknowledgements are authorized on the server. Actor identity is server-owned. WebSockets use authenticated, one-use 30-second admission tickets, an Origin allowlist and a negotiated medikiosk subprotocol. Tickets are process-local and sent in the subprotocol, not URLs. Deployment identity/session revocation and multi-worker messaging remain outside this prototype.

Voice consent is checked before invoking ASR and again when accepting source voice. Candidates are signed and bound to exact text, session, question, language and revision. They expire after 10 minutes or backend restart. Confirmation stores source/provider provenance; editing records typed wording. Candidates/audio are not stored as clinical answers before confirmation.

FastAPI/Starlette multipart parsing may spool uploads above its threshold to temporary disk before the service checks consent. Routes close uploaded files on success, failure and rejection. No audio is deliberately saved to PostgreSQL or object storage. Abrupt termination, OS temporary-file policy, memory zeroization and upstream provider retention are not covered by a claim of guaranteed erasure. Browser cancellation stops tracks and discards late callbacks/uploads.

Documents validate type, size and decoded content before database persistence. Local storage resolves paths and enforces containment; database failures trigger file cleanup. There is no atomic transaction spanning filesystem and SQL across process/power loss. Original document reads require staff authorization. Mock extraction is content-addressed synthetic fixture behavior, not OCR of arbitrary uploads; no confidence is invented.

NVIDIA sends only eligible text/language/field context, omitting identifying metadata. Identifiers embedded in free text or voice are **not automatically redacted**. Neither metadata minimization nor SecretStr constitutes complete de-identification. Provider keys remain in environment/local ignored files, are excluded from public configuration, and must never be logged or committed. BHASHINI callback targets are constrained, redirects/environment proxies disabled, payloads bounded and service calls deadline-limited. Live provider acceptance remains separate from mocked tests.

Unexpected errors log only exception class, not exception messages, submitted values, query strings or stack-local payloads. Audit events retain server actor/version/source linkage and review history in the database. Do not log raw audio, OCR text, answers, credentials or admission tokens.

Alert delivery uses bounded writes to authorized sockets and browser resynchronization. A successful write does not establish human receipt; patient copy asks for direct staff contact. Current trigger state and acknowledgement history are separate. Rule content is prototype/unvalidated; unknown language is not evidence of absence.

Security verification and outstanding acceptance gates are recorded in [stabilization status](stabilization-implementation-status.md). Full production authorization, encrypted deployment, consent revocation across active sessions, retention operations and crash-recovery controls require separate scope and review.

## Phase 7 access and audit boundary

Medical-fact, timeline, discrepancy, and fact-review APIs reuse the existing staff dependency and sharing-consent check. No parallel demo bypass or public patient fact endpoint was added. Reviewer ID and review time come from the server-resolved active doctor; extra caller-supplied identity fields are rejected.

Original clinical values and raw source remain immutable. Corrections are additive revisions with optimistic versions; confirmed/cancelled sessions reject mutations. Audit metadata records only fact identifiers, type, status, and version—not corrected clinical values. Raw fact/source content is not intentionally written to application logs.

This remains header-gated local demo authorization, not production authentication. Source-document links are still fetched through authorized backend routes. No production encryption, retention, tenant isolation, external identity, or clinical compliance claim follows from these controls.

## Phase 8 summary drafting, revision audit, and clinical boundaries

Summary drafting, review, regeneration, and confirmation endpoints reuse the existing server-resolved staff authorization and session sharing consent checks.

1. **Server-Enforced Actor Provenance**: `confirmed_by`, reviewer identity, and `actor_user_id` are determined exclusively by the authenticated server session. Any client attempt to forge reviewer ID in request bodies is rejected (validation error 422).
2. **Optimistic Concurrency Control**: All draft edit, regeneration, and confirmation requests require `expected_version`. Version conflicts return HTTP 409 `VERSION_CONFLICT` without modifying persisted data.
3. **Confirmed Record Immutability**: Upon clinical sign-off (`POST /summary/confirm`), the summary transitions to `confirmed` status with `confirmed_text` locked. Any subsequent edit or regeneration attempt fails closed with HTTP 409 `CONFIRMED_IMMUTABLE`.
4. **Append-Only Audit Trail**: Summary creation, clinician revisions, draft regenerations, and final confirmations append immutable `summary_revisions` records with explicit `actor_type` (`SYSTEM` vs `DOCTOR`), structured/text snapshots, and clinician review notes.
5. **Non-Diagnostic Clinical Safety Boundary**:
   - The deterministic summary drafting engine synthesizes only validated facts without diagnosing, prescribing, or inferring diseases.
   - Unknown and unaddressed fields are explicitly documented as missing.
   - AYUSH pathways are prominently badged with demonstration and supportive-documentation disclaimers.
   - Raw medical text and sensitive clinical observations are excluded from unsafe system logs.

## Phase 9 verification hardening and amendment security boundary

1. **Anti-Forgery on Amendments & Field Verifications**:
   - `POST /summary/amend` and `POST /field-verifications` resolve clinician identity exclusively from server session credentials (`current_user.id`).
   - Client-provided actor IDs or timestamps are disallowed and rejected.
2. **Confirmed Record Immutability Preserved**:
   - Filing an amendment (`POST /summary/amend`) never mutates or erases `confirmed_text`, `confirmed_by`, or `confirmed_at`.
   - The original confirmed clinical record remains permanently preserved in place and in audit history.
   - The amendment is stored in dedicated fields (`amended_text`, `amended_by`, `amended_at`, `amendment_notes`) and logged as a versioned addendum in `summary_revisions`.
3. **Optimistic Locking on Field Verifications**:
   - Field verification supports `expected_version` checks to prevent race conditions across multi-tab clinician reviews. Mismatches return HTTP 409 `VERSION_CONFLICT`.
4. **Session Audit Trail Access Control**:
   - `GET /audit-trail` is restricted to authorized staff (`X-Demo-Doctor: true`).
   - Audit logs capture actor classification (`DOCTOR`, `PATIENT`, `SYSTEM`), actions, and structured metadata without exposing raw secrets, authentication tokens, or uncontrolled diagnostic claims.

