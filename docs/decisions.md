# Architecture Decision Record Log — MediKiosk

Use this file for durable technical/product decisions.

Status values: `Accepted`, `Proposed`, `Superseded`.

---

## ADR-001 — Modular monolith for SIH prototype

**Status:** Accepted

**Decision:** Use one React frontend, one FastAPI backend, PostgreSQL, and optional object storage.

**Why:** The prototype needs rapid integration across six team members. Independent microservices would add deployment/networking/contract overhead without proving the core product.

**Consequence:** Maintain strong internal module boundaries so components can be extracted later if needed.

---

## ADR-002 — Two primary programming languages

**Status:** Accepted

**Decision:** TypeScript for user-facing web code; Python for backend/AI/medical processing.

**Why:** Reduces integration complexity while fitting the intended UI and AI ecosystem.

---

## ADR-003 — PostgreSQL as primary database

**Status:** Accepted

**Decision:** Use PostgreSQL rather than MongoDB.

**Why:** Core entities and relationships are relational: patients, sessions, consents, answers, documents, alerts, summaries, verification, audit.

---

## ADR-004 — Structured clinical data is canonical

**Status:** Accepted

**Decision:** The canonical internal state is validated structured data.

**Rejected alternatives:**
- raw interview transcript as source of truth;
- generated clinical paragraph as source of truth.

**Why:** Structured data supports deterministic rules, explainability, editing, testing, timeline generation, and interoperability.

---

## ADR-005 — LLM + deterministic control

**Status:** Accepted

**Decision:** Use LLMs for language understanding/extraction/summarization, but deterministic engines/configuration control required fields and safety logic.

**Why:** Better explainability and safer behavior than an unconstrained chat-agent interview.

---

## ADR-006 — Deterministic red-flag engine

**Status:** Accepted

**Decision:** Red flags are fired from versioned explainable rules over structured facts.

**Why:** Safety behavior must be testable and explainable.

---

## ADR-007 — One React app for all three interfaces

**Status:** Accepted

**Decision:** Use one React/Vite app with `/kiosk`, `/doctor`, and `/triage` route groups.

**Why:** Shared types/components, simpler build and deployment, less duplication.

**Revisit if:** Different interfaces later require independent release cycles or device-specific packaging.

---

## ADR-008 — External AI providers behind adapters

**Status:** Accepted

**Decision:** Speech, OCR fallback, and LLM provider calls must be hidden behind interfaces.

**Why:** Credentials/provider availability may change during the hackathon; development must remain possible with mocks.

---

## ADR-009 — FHIR as integration layer, not persistence model

**Status:** Accepted

**Decision:** Maintain a clear internal model and convert to FHIR after clinician-confirmed data is available.

**Why:** Keeps the application model practical while preserving interoperability.

---

## ADR-010 — ABDM integration late in build order

**Status:** Accepted

**Decision:** Demonstrate a robust local flow and FHIR export before live ABDM sandbox work.

**Why:** Avoid blocking the core prototype on external onboarding/API dependencies.

---

## ADR-011 — Preserve AI draft and clinician confirmation separately

**Status:** Accepted

**Decision:** Do not overwrite the generated/review draft when a doctor confirms the final record.

**Why:** Auditability and credibility.

---

## ADR-012 — Phase 1 runtime and contract reconciliation

**Status:** Accepted

**Decision:** Restore the documented React/Vite/TypeScript/Tailwind, FastAPI/Pydantic, SQLAlchemy/Alembic, PostgreSQL, ESLint/Prettier, and pytest/Vitest stack. Python dependencies are constrained to the verified environment; npm uses its lockfile. SQLite is restricted to tests.

The canonical REST prefix is `/api`. Patient and intake creation occur atomically through `POST /api/sessions`, with a client-generated UUID enabling safe retry. This replaces independently exposed patient CRUD in the initial contract. A resume snapshot includes the session, patient, consent, and latest saved answers. General patient/session/answer deletion and unrestricted update routes are not exposed.

Phase 1 uses five deterministic history fields. Draft complaint flows are retained for Phase 2 but are not loaded by the active frontend.

**Why:** The earlier scaffold could not complete an intake, used inconsistent API paths, and could duplicate patients after failed requests. One transactional creation boundary and typed, server-enforced workflow make the Phase 1 path testable.

**Consequence:** Frontend and backend must use the updated `docs/api-contract.md`. This is a local prototype contract change, not a promise to preserve the broken `/api/v1` scaffold.

## ADR-013 — Explicit demo identity and review integrity

**Status:** Accepted

**Decision:** Local doctor actions require explicitly configured `DEMO_MODE=true`, the seeded active doctor, and the demo request header. Demo mode is disabled under `APP_ENV=production`. This does not substitute for real staff authentication; patient UUIDs are also not a production access-control scheme.

The server owns consent gating, answer provenance, completion, reviewer identity, confirmation time, and summary state. Completion creates a deterministic draft from persisted answers. Review saves preserve that draft and append summary revisions. Expected versions and a PostgreSQL session-row lock protect concurrent edits; confirmed records are read-only. Audit events contain action metadata, not full clinical text.

**Why:** Phase 1 needs a repeatable doctor workflow without pretending production authentication or AI integration is available. Clinical confirmation must remain attributable and must not silently replace the draft.

**Consequence:** Implement real staff authentication and patient capability tokens before handling real data or exposing this app outside the local demonstration. Versioned amendments to confirmed records remain later hardening work.

## ADR-014 — Project-local Windows PostgreSQL and verification tools

**Status:** Accepted

**Decision:** For this configured Windows machine, provision PostgreSQL 18.6 binaries and data under ignored `.runtime/`, with SCRAM credentials, a dedicated app role, an application database, and a separate test database. Bind PostgreSQL to 127.0.0.1:55432. Run backend/frontend on 8010/5175 to avoid the existing services on the original ports. Provide explicit start/stop scripts and preserve the older SQLite files.

Add Playwright only for end-to-end browser tests, alongside pytest and Vitest/React Testing Library. Headless tests use synthetic records and do not access signed-in browser profiles.

**Why:** The user requested help setting up local PostgreSQL. A project-local installation avoids a system-wide Windows service while supporting real migration, transaction, and restart testing. Browser checks demonstrate the complete UI/API journey.

**Consequence:** Run the launcher after a machine restart. Portable setup is Windows-specific; separately managed PostgreSQL works with the documented manual commands. Docker packaging remains deferred.

## ADR template

```text
## ADR-NNN — Title

Status: Proposed / Accepted / Superseded

Context:
...

Decision:
...

Alternatives:
...

Consequences:
...

Revisit when:
...
```

## ADR-015 — Version-pinned deterministic interview and non-destructive branch history

**Status:** Accepted for Phase 2.

**Decision:** Author all flows under `ai/complaint_flows/` with startup-validated Pydantic configuration. Use ordered questions and a small equals/contains AND condition format referencing only earlier questions. Backend services own applicability, cursor and completion; React renders returned question types. Keep AYUSH in a distinct namespace and retain a backend-only legacy compatibility flow.

Persist the selected flow snapshot/version, cursor and optimistic revision in a one-to-one interview_run. A durable request-ID/payload-hash receipt prevents delayed answer retries from undoing later edits. Existing session-row locks serialize mutations. Answers remain append-only; current structured history contains only latest active facts. A branch becoming active again restores its latest saved answers and original provenance, showing them during traversal. Unknown/not-reported are explicit states; optional skipping is distinct from negative answers.

**Rationale:** Mutable source files must not reinterpret an ongoing or confirmed record. Deleting inactive answers would lose patient wording and correction provenance. Latest-value deduplication alone cannot distinguish a delayed retry from a new correction. Backend authority prevents frontend and API behavior drifting.

**Consequences:** One selected flow per intake; a new intake is required to choose a different complaint. Two additive tables are required for durable flow state and retry receipts. No dedicated clinical_history table is needed: active Pydantic history is computed and uses the existing summary JSON column for the completion snapshot. Future phases must preserve snapshot schema compatibility and distinguish restored historical answers from newly collected facts via their provenance.

## ADR-016 — Optional provider-neutral normalization snapshots

**Status:** Accepted for Phase 3A.

**Decision:** Eligible short-text fields are an explicit allowlist. A cancellable async provider protocol receives minimal text/field/language/context and returns untrusted structured output. The service validates a strict symptom/qualitative allowlist contract and assigns trusted display/value plus all provenance. Development/test defaults to an exact-match mock; disabled is explicit; unknown provider configuration fails startup. No external provider fallback exists.

Persist one immutable result snapshot per immutable answer ID, including unknown/unrecognized/provider failures. A savepoint isolates optional enrichment failures from source-answer persistence. Reads reuse snapshots; source corrections create new answers/results. Active branch filtering includes both reported and normalized representations. Reactivation restores the saved snapshot, without recomputation. Historical/confirmed records are never automatically backfilled. The reported answer and deterministic prose draft remain separate from machine enrichment.

**Rationale:** Normalization must not become the interview authority or a dependency whose failure loses raw answers. Derived facts need durable provenance and invalidation by source revision. Exact fixtures must not imply calibrated probabilities or clinical verification. Competing unvalidated provider/model paths were removed; a single additive normalization_results migration now matches runtime persistence.

**Consequences:** Future real providers must honor async cancellation and transport timeouts. There is no automatic reprocessing API; adding one needs explicit versioning/audit/confirmed-record semantics. The UI labels all machine facts not clinician verified even after summary confirmation. Future complaint candidates require explicit confirmation and currently have no active workflow caller.

---

## ADR-017 — NVIDIA NIM Hosted Clinical Normalization Integration

**Status:** Accepted for Phase 3B.

**Decision:** Integrate NVIDIA Build / NVIDIA NIM hosted inference (`https://integrate.api.nvidia.com/v1`, model: `google/gemma-4-31b-it`) as the first real normalization provider behind the existing `ClinicalNormalizationProvider` interface (`backend/app/services/nvidia_normalization.py`).

Enforce the following architectural invariants:
1. **Deterministic Interview Authority**: The interview engine remains purely deterministic. Gemma-4-31B never chooses questions, branches, detects red flags, prescribes, or diagnoses.
2. **Strict Input Minimization**: Transmit only `text`, `language`, and `canonical_field`. Prohibit transmission of patient names, demo ABHA IDs, hospital tokens, doctor identity, session history, or database identifiers.
3. **Structured Output Contract (Schema 1.1)**: Enforce explicit `polarity` (`present` / `absent`), `certainty` (`certain` / `uncertain`), `confidence: null` (prohibiting uncalibrated synthetic probabilities), and exact evidence substring matching against untouched source text. Strict Pydantic application validation (`LiveProviderResult`) is authoritative. Heuristic prose parsing and automatic fuzzy repairs are forbidden.
4. **Fault-Tolerant Persistence**: Patient answers commit atomically before normalization. Savepoint isolation ensures that any provider timeout, network error, authentication failure, HTTP 429/5xx, or validation failure records an explicit `unavailable` result snapshot with durable reason and latency metadata. Intake continues uninterrupted; silent fallback to mock is prohibited.
5. **Secret Protection**: `NVIDIA_API_KEY` is loaded from environment only, wrapped in Pydantic `SecretStr(exclude=True, repr=False)`, and never logged, returned in responses, serialized in configurations, or committed.
6. **Conservative Sampling**: Use `temperature=0`, `stream=False`, `max_tokens=768`, and `chat_template_kwargs={"enable_thinking": False}`.

**Rationale:** Clinical normalization is a constrained classification task requiring auditability, privacy preservation, and failure resistance. Gemma-4-31B serves strictly as an untrusted language translation and concept extractor, keeping human clinicians and deterministic software in control.

**Consequences:** Real API calls require an explicit opt-in environment flag (`CLINICAL_NORMALIZATION_PROVIDER=nvidia` and `NVIDIA_API_KEY`). The standard offline test suite and CI default to mock mode. Empirical evaluation scripts separate offline test guarantees from live upstream vendor availability.

---

## ADR-018 — Provider-Neutral Voice Input and Text-To-Speech Architecture

**Status:** Accepted for Phase 4A.

**Decision:** Establish a provider-neutral speech architecture decoupling the patient kiosk and interview engine from speech providers. Build the architecture using deterministic mock providers first (`MockSpeechProvider`, `DisabledSpeechProvider`), strictly deferring vendor integrations (Bhashini, AI4Bharat) to Phase 4B.

Enforce the following architectural invariants:
1. **Deterministic Interview Authority**: Speech providers never choose questions, alter branching logic, submit answers automatically, normalize clinical concepts, diagnose, prescribe, or trigger red flags. The `InterviewEngine` remains the sole clinical authority.
2. **Strict Candidate Confirmation Workflow**: Speech recognition (ASR) output is strictly an unconfirmed *candidate transcript*. It is NEVER automatically committed to interview state. The kiosk displays the candidate transcript prominently ("You said: ...") and requires explicit patient action via localized buttons: `Confirm`, `Edit`, `Record again`, or `Cancel`.
3. **Zero Raw Audio Retention (Ephemeral Audio)**: Audio is never saved to PostgreSQL, object storage, or permanent filesystem. Temporary files created on the backend for provider communication are managed with strict context managers / `try...finally` blocks and deleted immediately upon success, provider failure, timeout, validation rejection, or unexpected exception. Audio blobs in browser memory are ephemeral and released immediately.
4. **Mandatory Voice Consent**: Voice processing requires explicit opt-in consent (`voice_processing: true`) at intake. The backend strictly enforces this via HTTP 403 `VOICE_CONSENT_REQUIRED`. The frontend hides microphone input controls when voice consent is not granted.
5. **Accurate Provenance Preservation**: Only after explicit patient confirmation does a transcript submit to the standard answer API. When confirmed without editing, it persists with `source: 'voice'`. If the patient edits the candidate transcript prior to confirmation, it persists with `source: 'typed'` to ensure patient-authored wording is never misrepresented as machine transcription.
6. **Isolated Downstream Normalization**: ASR produces text only. The Phase 3 clinical normalization pipeline operates downstream exclusively after explicit patient confirmation and answer persistence. The speech provider knows nothing about clinical ontologies; the normalization provider knows nothing about audio.
7. **Strict Question TTS Scope**: Text-to-speech synthesizes strictly the exact localized question text from the pinned complaint flow snapshot (`InterviewEngine`). Dynamic prose generation, patient answers, clinical histories, and doctor summaries are strictly prohibited from TTS synthesis. Audio playback is strictly user-initiated ("Listen"); auto-play is prohibited.
8. **Graceful Fallback**: Microphone input is strictly an adjunct input method for spoken responses (`short_text` question types). Touch and type controls remain available at all times. On permission denial, audio format error, upload failure, or provider timeout, the UI cleanly falls back to touch/type input without disrupting the deterministic interview flow.

**Rationale:** Voice capture in a clinical kiosk carries acute privacy, safety, and accuracy risks. Unconfirmed speech transcription error rates in Indian languages/accents are high; treating raw ASR as clinical fact would risk patient harm. By enforcing candidate confirmation, zero raw audio storage, explicit consent, and strict input/output boundaries, MediKiosk achieves conversational accessibility while maintaining clinical explainability and data protection.

**Consequences:** Speech providers are swappable via `SPEECH_PROVIDER` environment configuration (`mock`, `disabled`, and future `bhashini`). Database schema required zero migrations since `source` was already an unconstrained string column. Offline unit and browser tests run deterministically with synthetic fixtures, eliminating microphone hardware or external service dependencies in CI.

---

## ADR-019 — Deterministic Red-Flag Safety Screening & Staff Triage Dashboard

**Status:** Accepted for Phase 5.

**Decision:** Implement deterministic safety screening rules (`ai/safety_rules/red_flags_v1.json`) evaluated by a pure safety engine (`backend/app/services/red_flags.py`) upon answer submission during pre-consultation intake. Persist structured safety alerts in an additive PostgreSQL `alerts` table (`backend/alembic/versions/f54c306d1e24_red_flag_alerts.py`) and surface real-time notifications via WebSocket to the Staff Triage Dashboard (`/triage`) and Doctor Workspace (`/doctor`).

Enforce the following architectural invariants:
1. **Strictly Deterministic Safety Logic**: Large language models (LLMs) and neural networks are strictly forbidden from deciding red-flag safety statuses or priority levels. All safety screening is evaluated deterministically over structured patient-reported facts and validated normalized concepts.
2. **Authoritative Versioned Rule Catalog**: Safety rules are maintained in a versioned JSON catalog (`ai/safety_rules/red_flags_v1.json`) with explicit rule IDs (e.g. `RF-CHEST-001`), flow scoping, priority levels (`emergency` vs `urgent`), clinical categories, and declarative conditions (`greater_than_or_equal`, `equals`, `contains`, `contains_any_word`, concept matching).
3. **Idempotent Alert Persistence**: The database enforces a unique constraint `uq_session_rule_alert` on `(session_id, rule_id)`. Re-evaluating rules on question updates modifies existing alert records rather than generating duplicate notifications. If triggering conditions are resolved by subsequent patient answer edits, the alert status transitions to `resolved`.
4. **Calm Non-Diagnostic Patient Advisory**: When an emergency or urgent alert triggers, the Kiosk UI displays a calm, reassuring advisory banner (`docs/design.md` Section 8): *"Potential emergency symptoms were detected. Medical staff should assess you promptly. Please contact medical staff directly; this prototype does not guarantee notification."* Diagnostic claims (e.g., "You are having a myocardial infarction") to the patient are strictly prohibited.
5. **Real-time Staff Escalation & Acknowledgment**: Alerts are broadcast immediately to connected triage staff clients via WebSocket (`/api/triage/ws`). Triage staff can review triggering clinical evidence and acknowledge alerts with their staff name/ID and action notes, creating an auditable provenance trail.
6. **Physician Visibility**: Active and acknowledged alerts are preserved alongside clinical history in session detail endpoints and highlighted in the doctor workspace to ensure the reviewing physician has full awareness of emergency findings.

**Rationale:** Clinical safety screening in a hospital reception kiosk requires absolute predictability, zero hallucination risk, and rapid clinical escalation. Pure deterministic rule evaluation over structured facts guarantees safety bounds while real-time WebSocket feeds enable clinical staff to prioritize acute patients before physician consultation.

**Consequences:** The `alerts` table is additive with zero impact on existing patient/session rows. The kiosk interface provides immediate patient reassurance without causing panic. The staff triage dashboard provides real-time situational awareness across all active kiosk sessions.

---

## ADR-020 — BHASHINI (ULCA) Real Speech Provider Integration

**Status:** Accepted for Phase 4B.

**Decision:** Integrate the Government of India's **BHASHINI (ULCA)** Speech Platform as a real speech recognition (ASR) and text-to-speech (TTS) provider behind MediKiosk's provider-neutral `SpeechProvider` interface (`backend/app/services/bhashini_speech.py`).

Enforce the following architectural invariants:
1. **Zero LLM or ASR Decision Authority**: Bhashini ASR and TTS models have zero authority over question sequencing, branching, answer commitment, concept normalization, or red-flag detection. The `InterviewEngine` remains the sole clinical authority.
2. **Mandatory Candidate Transcript Confirmation Gate**: ASR transcripts returned by Bhashini are strictly candidate suggestions. They are **never** committed directly to interview state or clinical history. The patient must explicitly confirm the candidate transcript via the kiosk UI (`[Confirm]`, `[Edit]`, `[Record again]`, or `[Cancel]`).
3. **Ephemeral Audio & Zero Raw Audio Retention**: In compliance with [`docs/security-privacy.md`](security-privacy.md), patient voice recordings are never saved to PostgreSQL, object storage, or permanent disk. Multipart parsing may spool audio to temporary disk before service consent checks. The route closes the upload on success, rejection, timeout or failure; no permanent audio retention is intentionally implemented.
4. **Dual Architecture Support (ULCA Pipeline Discovery & Direct Inference)**: The adapter supports both standard two-step Bhashini ULCA pipeline discovery (`/ulca/apis/v0/model/getModelsPipeline` + compute callback) with in-memory pipeline config caching (1-hour TTL), as well as pre-configured direct inference compute endpoints (`BHASHINI_INFERENCE_URL` / `BHASHINI_INFERENCE_API_KEY`) for self-hosted or dedicated deployments (e.g. AI4Bharat / Dhruva).
5. **Zero Secret Leakage**: All API keys, user IDs, and inference bearer tokens are handled using Pydantic `SecretStr(exclude=True, repr=False)` and are excluded from logging, serialization, and API responses.
6. **Graceful Degradation & Bounded Latency**: Upstream timeouts, network interruptions, 401/403 authentication rejections, 429 rate limits, and 5xx errors return explicit `status: "unavailable"` results with technical reasons (`timeout`, `authentication_failed`, `rate_limited`, `provider_error`) without crashing the application or rolling back patient progress. The kiosk seamlessly displays a localized fallback notice and keeps touch/type controls active.
7. **Offline Mock Independence**: The default configuration remains `SPEECH_PROVIDER=mock`, requiring zero secrets and zero network calls, ensuring automated CI runs and local development environments remain completely isolated and reproducible.
8. **Zero Database Migrations**: `answers.source` is an unconstrained string column supporting `"voice"` and `"typed"`. No schema modifications or database migrations are required.

**Rationale:** Integrating India's national language translation and speech stack (BHASHINI / AI4Bharat) enables conversational accessibility for diverse linguistic backgrounds (English, Bengali, Hindi) without compromising patient data privacy, clinical explainability, or software determinism.

**Consequences:** Operators can configure live Bhashini integration by setting `SPEECH_PROVIDER=bhashini`, `BHASHINI_API_KEY`, and `BHASHINI_USER_ID`. CI, automated test suites, and offline developer workflows continue to run against mock providers. Diagnostic evaluation can be performed via `scripts/evaluate-bhashini-speech.py`.

## ADR-021 — Stabilization supersedes Phase 4–6 completion assumptions

2026-09-10: Follow the independent audit. Preserve Phase 1–3; add no roadmap feature/provider/database. Reuse server demo identity on staff routes. Use single-use origin-checked socket tickets, versioned alert evidence/reviews and audit history. Restrict raw-language matching to explicit prototype phrases; do not invent clinical criteria. Separate canned document fixtures from arbitrary uploads and preserve null flags. Require signed ASR candidates and disclose multipart temporary-disk handling. This supersedes prior claims of guaranteed notification, memory-only multipart audio, live BHASHINI acceptance or completed real OCR. See stabilization status for evidence and remaining gates.


## ADR-022 — Repair existing Phase 7 without expanding it

2026-09-10: The user explicitly requested review and fixes for Phase 7 code written after stabilization. Its migrations were already applied. Preserve the deployed singular tables and generic timeline columns; align ORM models and add missing indexes through a forward migration. Materialize only the current typed medication/lab contract, validate before insertion, preserve source, isolate failures and make retry idempotent. Do not add unsupported timeline-note types, events, diagnoses or new providers. Dedicated timeline/discrepancy/fact-review workflows remain absent. This authorization does not establish completion of the earlier database-restart acceptance gate.

## ADR-023 — Computed Phase 7 timeline and additive fact review

**Status:** Accepted

2026-09-10: After explicit authorization to complete Phase 7, derive timeline and discrepancy responses deterministically from current source facts instead of materializing timeline rows. Preserve the existing timeline table without a producer. Keep extracted fact values immutable and store every clinician verification/rejection/correction as an optimistic, additive `medical_fact_revisions` row with server-owned attribution. This supersedes ADR-022 only for its prior scope restriction; its repair and preservation decisions remain active.

## ADR-024 — Sarvam REST speech behind the existing provider boundary

**Status:** Accepted

2026-09-11: Add Sarvam as an explicitly selected `SPEECH_PROVIDER=sarvam` implementation without changing the provider-neutral interview workflow. Use the exact official Python SDK `sarvamai==0.1.31a4` only in the backend; never expose `SARVAM_API_KEY` to the browser. Pin `saaras:v3` for same-language transcription and `bulbul:v3`/`shubh` for 16-kHz WAV question audio. Map en/bn/hi to BCP-47 `-IN` codes, set SDK retries to zero, and keep a 12-second provider timeout inside the existing 15-second application deadline.

Sarvam receives only consented, current-question 16-kHz mono PCM16 WAV input. Its transcript remains an unconfirmed signed candidate and cannot bypass confirmation or provenance controls. TTS remains limited to pinned question text. Mock and BHASHINI providers remain available; live selection is explicit so merely storing a key cannot trigger billable network calls. The successful Bengali synthetic TTS-to-ASR loopback establishes REST transport only, not physical microphone, accent, or clinical accuracy acceptance.

---

## ADR-025 — Sarvam Translation, Language Identification, and Document Intelligence Integration

**Status:** Accepted

**Decision:**
1. **Translation (`mayura:v1`) & Transliteration**:
   - Implemented behind the `TranslationProvider` abstraction (`backend/app/services/sarvam_translation.py`).
   - Exposed as staff-assisted on-demand tools in the Doctor Workspace (`POST /api/doctor/sessions/{session_id}/translate` and `transliterate`).
   - **Immutability of Source Truth**: Patient-reported answers and raw wording remain strictly immutable. Translations are returned and presented alongside original wording with complete provenance metadata (source language, target language, provider, model, timestamp) and never overwrite or alter canonical clinical facts.
2. **Language Identification**:
   - Used for assisting staff and validation; it never overrides the patient's explicitly chosen language at intake.
3. **Document Intelligence / OCR (`doc-ai-digitise-v1`)**:
   - Implemented behind the `OcrProvider` abstraction (`backend/app/services/sarvam_ocr.py`) via official SDK `SarvamAI.doc_ai.digitise`.
   - Bounded execution: Polled at 0.5s intervals up to 16 polls (8s maximum window) with a 15s overall timeout.
   - Preserves typed file validation, size limits (<= 10MB), and content-addressed storage.
   - Outputs assembled markdown text and markdown/HTML tables with strictly nullable confidence (`None`), preventing hallucinated confidence numbers.
   - Non-negotiable clinical boundary: OCR extraction is explicitly marked unverified until a clinician reviews and confirms or rejects it. No medical values, dates, or diagnoses are invented.
4. **Dubbing & Streaming Exclusion**:
   - Sarvam Dubbing is excluded from the clinical intake loop because MediKiosk uses ephemeral question text and voice input rather than pre-recorded media dubbing.
   - WebSocket streaming ASR/TTS is intentionally excluded: the REST ASR endpoint achieves ~0.36s latency, so adding streaming WebSocket proxying would increase session security complexity without meaningful clinical benefit.
5. **Security & Credentials**:
   - `SARVAM_API_KEY` remains strictly backend-side in `backend/.env`. It is never returned to the frontend or included in public config (`/api/config` only reveals provider name `sarvam`).

---

## ADR-026 — Hardened Strict Role-Based Access Control (RBAC) and Triage Isolation

**Status:** Accepted

**Context:**
MediKiosk operates in clinical healthcare environments where patients authenticate at physical kiosks via phone number OTP, while clinical review and emergency triage are managed by distinct hospital staff roles. Patient phone OTP authentication must never confer clinician or triage capabilities, and triage responders must not automatically inherit full doctor workspace permissions.

**Decision:**
1. **Three Dedicated Roles:**
   - `patient`: Authenticated via phone OTP or patient demo login. Can only access `/kiosk/*` and patient intake sessions where `session.patient_id == user.id`.
   - `doctor`: Authenticated clinical staff. Has exclusive access to `/doctor/*`, clinical fact verification/rejection, summary generation/confirmation, document verification, timeline discrepancies, FHIR exports, and ABDM operations. Blocked from `/triage`.
   - `triage`: Authenticated operational triage staff. Has access to `/triage`, emergency red-flag alert queue, acknowledgement/escalation, and live emergency WebSocket. Blocked from `/doctor/*` and direct patient intake.
2. **Backend Defense-in-Depth:**
   - Dedicated FastAPI dependencies in `backend/app/api/deps.py`: `require_doctor`, `require_triage`, `require_staff`, `require_patient`.
   - Unauthenticated requests receive HTTP 401 (`UNAUTHORIZED`).
   - Unauthorized role attempts receive HTTP 403 (`FORBIDDEN`).
   - Triage endpoints (`/api/triage/alerts`, `/api/triage/ws-ticket`, `/api/triage/alerts/{id}/acknowledge`) protected with `require_triage`.
   - Doctor endpoints (`/api/doctor/*`, `/api/fhir/*`, `/api/abdm/*`) protected with `require_doctor`.
   - Patient intake endpoints enforce `verify_session_access` ensuring patients only access their own sessions and triage staff cannot inspect patient intake.
3. **WebSocket Security:**
   - Live triage alerts (`/api/triage/ws`) mandate an ephemeral, cryptographically secured ticket via `/api/triage/ws-ticket`.
   - Tickets are role-verified in `admit_websocket`: non-staff and patient connections are disconnected immediately with close code 1008 (Policy Violation).
4. **Frontend Route & Navigation Guards:**
   - `ProtectedRoute` enforces `allowedRoles`. When unauthorized, it displays a strict "Doctor Access Required" or "Triage Access Required" screen and never renders protected child components or leaks data.
   - Header navigation dynamically filters visible navigation items based on the active role.
   - Direct browser URL changes or page reloads maintain complete role enforcement.
