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
