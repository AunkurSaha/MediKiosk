# Architecture — MediKiosk

Current implementation is Phase 5; see the implemented boundaries at the end and [status](phase5-implementation-status.md). The broader module/deployment diagrams describe the target roadmap, including unimplemented future integrations.

## 1. Architectural style

For the SIH prototype, use a **modular monolith**:

- one React frontend;
- one FastAPI backend;
- one PostgreSQL database;
- optional MinIO object storage;
- internal modules/adapters for AI and integration providers.

Do not deploy every conceptual “service” independently.

## 2. Logical architecture

```text
┌──────────────────────────────────────────────────────────────┐
│                       React Frontend                         │
│                                                              │
│   /kiosk/*              /doctor/*              /triage/*     │
│   Patient UI            Doctor UI              Staff UI      │
└──────────────────────────────┬───────────────────────────────┘
                               │
                         REST / WebSocket
                               │
┌──────────────────────────────▼───────────────────────────────┐
│                        FastAPI Backend                       │
│                                                              │
│  API layer                                                   │
│      │                                                       │
│      ├── Session / Identity / Consent                        │
│      ├── Interview Engine                                    │
│      ├── Clinical Normalization Adapter                      │
│      ├── Safety / Red-Flag Engine                            │
│      ├── Speech Adapter                                      │
│      ├── Document / OCR / Extraction Pipeline                │
│      ├── Timeline + Discrepancy Engine                       │
│      ├── Summary Generator                                   │
│      ├── Doctor Verification                                 │
│      ├── FHIR Adapter                                        │
│      └── Audit                                               │
└───────────────┬───────────────────────┬──────────────────────┘
                │                       │
          PostgreSQL               MinIO/S3
       structured data          original documents
```

## 3. Frontend architecture

Use one Vite application with route namespaces.

Suggested feature boundaries:

```text
frontend/src/
├── app/
├── routes/
│   ├── kiosk/
│   ├── doctor/
│   └── triage/
├── features/
│   ├── identification/
│   ├── consent/
│   ├── interview/
│   ├── documents/
│   ├── alerts/
│   ├── timeline/
│   └── summary/
├── components/
├── api/
├── types/
└── i18n/
```

Avoid duplicating clinical types separately in many files. Keep API response types centralized.

## 4. Backend modules

Suggested:

```text
backend/app/
├── main.py
├── api/
│   ├── health.py
│   ├── patients.py
│   ├── sessions.py
│   ├── consent.py
│   ├── interview.py
│   ├── documents.py
│   ├── alerts.py
│   ├── doctor.py
│   └── exports.py
├── core/
│   ├── config.py
│   ├── security.py
│   └── logging.py
├── db/
│   ├── base.py
│   └── session.py
├── models/
├── schemas/
└── services/
    ├── interview_engine.py
    ├── clinical_normalizer.py
    ├── red_flag_engine.py
    ├── speech.py
    ├── ocr.py
    ├── document_extractor.py
    ├── timeline.py
    ├── discrepancies.py
    ├── summarizer.py
    ├── fhir.py
    └── audit.py
```

## 5. Canonical clinical representation

The most important architectural rule:

**Raw patient text is not the canonical record. Generated prose is not the canonical record.**

The canonical representation is structured data.

Conceptual shape:

```json
{
  "session_id": "uuid",
  "chief_complaints": [],
  "hpi": {},
  "past_medical_history": [],
  "past_surgical_history": [],
  "medications": [],
  "allergies": [],
  "family_history": [],
  "personal_history": {},
  "review_of_systems": {},
  "document_facts": [],
  "alerts": [],
  "discrepancies": []
}
```

The exact schema can evolve, but every external AI output must be converted into validated structured fields before downstream use.

## 6. Interview pipeline

```text
Patient answer
→ preserve raw/original answer
→ normalize into known clinical field(s)
→ validate against schema
→ update structured history
→ run safety rules
→ determine missing required fields
→ select next question
```

Question selection should use:
- complaint-flow configuration;
- completion state;
- deterministic branch rules;
- optional language-generation/normalization help.

## 7. Speech architecture

Use an interface:

```text
SpeechService
├── transcribe(audio, language)
└── synthesize(text, language)
```

Possible implementations:
- mock;
- BHASHINI;
- AI4Bharat/self-hosted;
- another explicitly approved provider.

Frontend should not depend on provider-specific API shape.

## 8. Red-flag architecture

```text
Structured clinical facts
→ deterministic versioned rules
→ zero or more Alert objects
→ persistence
→ WebSocket event
→ Triage Dashboard
```

Alert must contain:
- rule ID/version;
- severity;
- reason;
- triggering facts;
- created time;
- acknowledgement info.

LLM output alone must never create a non-explainable emergency classification.

## 9. Document pipeline

```text
upload
→ persist original file
→ classify document
→ preprocess image if needed
→ OCR
→ preserve OCR output/confidence
→ structured extraction
→ validation
→ timeline facts
→ discrepancies
→ doctor verification state
```

Object storage should hold source files. PostgreSQL holds metadata and extracted structured facts.

## 10. Summary pipeline

```text
validated structured history
+ validated document facts
+ explicit alert/discrepancy state
→ summary generator
→ structured/draft summary
→ doctor edits
→ doctor confirms
→ confirmed record
```

The summarizer receives structured data, not an uncontrolled full chat dump.

## 11. FHIR boundary

FHIR is an adapter layer after internal clinical data stabilizes.

Do not make internal persistence exactly mirror FHIR from day one.

Instead:

```text
MediKiosk internal model
→ FHIR adapter
→ validated FHIR JSON/Bundle
→ HIS/ABDM connector
```

## 12. Failure behavior

External provider failure must degrade gracefully:

- ASR fails → touch/type fallback.
- TTS fails → text remains visible.
- LLM fails → deterministic interview continues where possible.
- OCR fails → original document remains available, mark extraction unavailable.
- object storage fails → do not claim upload succeeded.
- WebSocket fails → alerts remain persisted and visible on dashboard refresh.
- ABDM unavailable → local FHIR export still works.

## 13. Deployment

Prototype target:

```text
docker compose
├── frontend
├── backend
├── postgres
└── minio   # when document phase is enabled
```

Redis is intentionally omitted initially.

## 14. Security boundaries

Never expose:
- database credentials to frontend;
- provider secret keys to frontend;
- raw internal stack traces to end users;
- unrestricted document object URLs.

Use backend-authorized access.

## 15. Scalability posture

For SIH, correctness and a complete demo matter more than premature scale.

Module boundaries are chosen so high-load components can be separated later if required.

## Implemented Phase 2 boundary

Sections describing voice, real normalization providers, safety, documents, WebSockets, FHIR and deployment above are target architecture for later phases. The current runnable app is a REST-only modular monolith with local PostgreSQL; those integrations remain unimplemented.

The active path is:

```text
Consent + explicit patient complaint selection
→ validated ai/complaint_flows configuration
→ pinned InterviewRun snapshot/version
→ typed patient answer + append-only persistence
→ pure InterviewEngine applicability/traversal
→ Pydantic ClinicalHistory from active answers
→ deterministic draft + doctor review/confirmation
```

`schemas/flow.py` defines the small declarative language; `services/flow_registry.py` validates it at startup. `services/interview_engine.py` contains pure evaluation and assembly. `services/adaptive.py` manages transactions, cursor/revision, consent, receipts and history reads. FastAPI handlers only dispatch typed requests. The React Interview container and QuestionRenderer render server state by input type; no frontend clinical flow source remains.

Branch evaluation proceeds in configuration order and only considers active answered parent facts. Inactive historical answers cannot activate descendants. Parent corrections preserve all rows. Reactivated branches restore the latest saved values with original provenance; forward traversal exposes them for review.

Each selection pins the validated configuration to prevent later source edits reinterpreting an ongoing record. Request UUID/hash receipts make delayed retries safe even after subsequent corrections. The existing session-row lock serializes mutations. Optimistic interview revisions prevent stale tabs from changing the current answer.

ClinicalHistory has typed canonical sections, raw wording, typed values, explicit missing-information status and answer provenance. It is computed during intake and snapshotted in the existing summary JSON column at completion. Future normalization consumes this structure and produces separately validated facts; it must not replace raw source wording or take over deterministic question selection. See ADR-015 and the [Phase 2 status](phase2-implementation-status.md).

## Implemented Phase 3A normalization boundary

Phase 3A now adds a provider-neutral normalization service with a deterministic local mock; real providers remain deferred. The InterviewEngine is unchanged and never reads normalization to choose questions or evaluate conditions.

Eligible short_text + explicit field policy → immutable reported answer → bounded provider call → strict ProviderResult validation → trusted symptom/qualitative catalog → durable NormalizationResult → additive Fact.normalization in active history. No provider call occurs in route handlers, GET/history reads, replay or confirmation. Typed values and AYUSH bypass language normalization.

The service uses savepoints so failed enrichment writes/reads do not poison the surrounding patient-answer transaction. Explicit statuses distinguish normalized, unknown, unrecognized and unavailable. Provider exceptions are not echoed/logged with patient text. Persisted results attach to immutable answer IDs; current-source/branch filtering is inherited from Phase 2. No automatic reprocessing/backfill changes existing records.

The future candidate helper returns explicit-confirmation suggestions only and has no caller in the current workflow. Vendor adapters must implement cancellable async I/O, structured output and transport timeouts. See ADR-016 and [Phase 3A verification](phase3a-implementation-status.md).

## Implemented Phase 3B NVIDIA NIM normalization provider

Phase 3B integrates NVIDIA Build / NVIDIA NIM hosted inference (`https://integrate.api.nvidia.com/v1`, model: `google/gemma-4-31b-it`) behind the provider-neutral boundary via `NvidiaClinicalNormalizationProvider`:

```text
Eligible patient answer committed
    ↓
NormalizationService (savepoint isolated)
    ↓
NvidiaClinicalNormalizationProvider
    ├── Input minimization: text, language, canonical_field only
    ├── HTTP client: httpx2 with strict transport timeout (8-15s) and 64KB response cap
    ├── Model parameters: temperature=0, stream=false, max_tokens=768, chat_template_kwargs={"enable_thinking": false}
    └── SecretStr authentication: NVIDIA_API_KEY from environment only, never serialized or logged
    ↓
Strict application validation: LiveProviderResult (Schema 1.1)
    ├── concept from authoritative catalog
    ├── evidence: exact contiguous substring of source text
    ├── polarity: explicit "present" | "absent"
    ├── certainty: "certain" | "uncertain"
    └── confidence: null (prohibits synthetic probabilities)
    ↓
normalization_results: snapshot persisted with provider, model, prompt_version, latency_ms, token_usage
    ↓
Active clinical history & doctor UI: machine facts labeled "not clinician verified" alongside raw wording
```

If NVIDIA fails, times out, or returns invalid schema:
- The raw patient answer remains safely persisted in PostgreSQL.
- Normalization records an explicit `unavailable` result with the specific failure reason (`timeout`, `network_error`, `authentication_failed`, `rate_limited`, `server_error`, `invalid_result`).
- The interview continues deterministically without silent fallback to mock.
- Offline development and CI remain default: `CLINICAL_NORMALIZATION_PROVIDER=mock` runs completely offline without an API key. See ADR-017 and [Phase 3B implementation status](phase3b-implementation-status.md).

## Implemented Phase 4A provider-neutral voice input and TTS architecture

Phase 4A introduces a provider-neutral speech architecture decoupling speech recognition (ASR) and text-to-speech (TTS) synthesis from vendor APIs:

```text
PATIENT VOICE RECORDING:
Browser microphone
    ↓
MediaRecorder API (WebM/Opus or browser default)
    ↓
POST /api/sessions/{session_id}/interview/speech/transcribe (multipart audio)
    ├── Consent guard: requires voice_processing == true (HTTP 403 if false)
    ├── Validation: MIME type, non-empty, 5MB file cap
    ├── Ephemeral file: server-generated temp file unlinked in finally block
    ↓
SpeechService → MockSpeechProvider (or future BhashiniSpeechProvider)
    ↓
TranscriptionResult (candidate transcript, null confidence, provider metadata)
    ↓
Candidate Review Card ("You said: ...")
    ├── [ Confirm ] → POST /api/sessions/{session_id}/interview/answers (source: 'voice')
    ├── [ Edit ]    → inline editing → POST .../answers (source: 'typed')
    ├── [ Record again ] / [ Cancel ]
    ↓
Standard Answer Persistence & History Update
    ↓
Phase 3 Clinical Normalization Pipeline (downstream only)
    ↓
InterviewEngine deterministically chooses next question

QUESTION TEXT-TO-SPEECH (TTS):
Patient presses [ Listen ] / [ শুনুন ] / [ सुनें ]
    ↓
POST /api/sessions/{session_id}/interview/speech/synthesize
    ├── Pinned complaint flow snapshot provides EXACT localized question text
    ├── Clinical history, prior answers, and doctor summaries are strictly excluded
    ↓
SpeechService → MockSpeechProvider (synthesizes deterministic audio payload)
    ↓
Browser Audio Playback
```

## 15. Implemented Phase 5 Boundaries — Deterministic Red-Flag Safety & Staff Triage Dashboard

Phase 5 implements deterministic, rule-based clinical safety screening and real-time triage escalation without any LLM decision-making.

```text
PATIENT SUBMITS ANSWER:
POST /api/sessions/{session_id}/interview/answers
    ↓
Answer persisted atomically & audit logged
    ↓
Phase 3 Clinical Normalization (optional短-text concepts)
    ↓
Pure Safety Engine Evaluation (backend/app/services/red_flags.py)
    ├── Input: Active facts + normalized concepts (machine_normalized, polarity: present)
    ├── Catalog: ai/safety_rules/red_flags_v1.json (11 deterministic rules)
    │   ├── RF-CHEST-001/002/003 (Cardiovascular: emergency / urgent)
    │   ├── RF-RESP-001/002     (Respiratory: emergency / urgent)
    │   ├── RF-FEV-001/002      (Infectious: emergency / urgent)
    │   ├── RF-HEAD-001/002     (Neurological: emergency / urgent)
    │   └── RF-ABD-001/002      (Gastrointestinal: emergency / urgent)
    ↓
Database Persistence:
    ├── Table: alerts (additive migration: f54c306d1e24_red_flag_alerts.py)
    ├── Idempotency: Unique constraint uq_session_rule_alert(session_id, rule_id)
    └── Resolution: Status automatically transitions to 'resolved' if answer changes
    ↓
Real-Time Escalation:
    ├── Kiosk Response: InterviewState.red_flag_alert attached (highest active priority)
    │   └── Kiosk UI displays calm, non-diagnostic safety advisory banner
    └── WebSocket Broadcast: /api/triage/ws
        ├── Event: alert_created / alert_acknowledged
        └── Staff Triage Dashboard (/triage): Live counter & interactive alert cards
            ├── Acknowledge action with staff ID and action note
            └── Physician Workspace (/doctor/sessions/:id): Safety alerts highlighted
```

Key Phase 5 Invariants:
1. **Zero LLM Safety Authority**: Large language models never evaluate red flags, assign priorities, or decide triage status. All rules are purely deterministic comparisons against structured data.
2. **Calm Non-Diagnostic Patient Notice**: The kiosk advisory banner strictly follows `docs/design.md` Section 8: *"Potential emergency symptoms were detected. Medical staff should assess you promptly. Medical staff have been notified."* Diagnostic statements to patients are strictly forbidden.
3. **Additive Persistence**: The `alerts` table is purely additive with zero impact on existing patient or session tables.
4. **Staff Accountability**: Acknowledgement captures staff name/ID, timestamp, and action note, persisted with full audit logging.

## 16. Implemented Phase 4B — BHASHINI (ULCA) Real Speech Provider Integration

Phase 4B connects the Government of India's **BHASHINI (ULCA)** Speech Platform as a real speech-to-text (ASR) and text-to-speech (TTS) provider behind MediKiosk's existing Phase 4A provider-neutral speech boundary (`SpeechProvider` protocol).

```text
PATIENT SPOKEN INPUT (WebM/Opus / WAV):
Browser MediaRecorder
    ↓
POST /api/sessions/{session_id}/interview/speech/transcribe (ephemeral bytes in memory)
    ↓
SpeechService → BhashiniSpeechProvider (backend/app/services/bhashini_speech.py)
    ├── Input minimization: audio bytes + target language ('en', 'bn', 'hi')
    ├── Pipeline Discovery (POST https://meity-auth.ulca.ai/ulca/apis/v0/model/getModelsPipeline)
    │   └── In-memory cache for discovered callbackUrl & serviceId (1-hour TTL)
    │   └── Alternatively: direct compute endpoint (BHASHINI_INFERENCE_URL)
    ├── Compute Inference (POST callbackUrl with Authorization header)
    │   └── Payload: base64-encoded audio, taskType: 'asr', audioFormat: 'webm' | 'wav' | 'ogg'
    ↓
Candidate TranscriptionResult (status: 'success' | 'unavailable', transcript: str, confidence: null)
    ↓
Candidate Confirmation Gate (Kiosk UI):
    ├── [ Confirm ] → commits to PostgreSQL with source: 'voice'
    ├── [ Edit ]    → inline editing → commits to PostgreSQL with source: 'typed'
    └── [ Retry ] / [ Cancel ]
    ↓
Ephemeral Audio Cleanup: Audio bytes discarded immediately from memory; zero disk/DB retention.

QUESTION TEXT-TO-SPEECH (TTS):
Patient clicks [ Listen ] / [ শুনুন ] / [ सुनें ]
    ↓
POST /api/sessions/{session_id}/interview/speech/synthesize
    ├── Pinned complaint flow snapshot provides EXACT localized question text
    ↓
SpeechService → BhashiniSpeechProvider
    ├── Pipeline Discovery (taskType: 'tts', sourceLanguage)
    ├── Compute Inference (inputData: localized text, gender: 'female')
    ↓
SpeechSynthesisResult (status: 'success', audio_base64: str, media_type: 'audio/wav')
    ↓
Browser Audio Playback
```

Key Phase 4B Invariants:
1. **Candidate Confirmation Mandatory**: Transcripts returned by Bhashini ASR are strictly unconfirmed candidates. They never commit automatically to interview state or clinical history.
2. **Zero Audio Retention**: Audio is never written to PostgreSQL, object storage, or permanent disk. Server-side memory buffers are released immediately upon completion.
3. **Dual Pattern Support**: Operates seamlessly with standard Bhashini ULCA pipeline discovery or pre-configured direct inference gateways (e.g. AI4Bharat / Dhruva).
4. **Secret Protection**: `BHASHINI_API_KEY`, `BHASHINI_USER_ID`, and `BHASHINI_INFERENCE_API_KEY` are wrapped in `SecretStr(exclude=True, repr=False)`.
5. **Zero Database Migrations**: Relational schema remains identical; `answers.source` already supports `"voice"` and `"typed"`.
6. **Offline Mock Independence**: The default `SPEECH_PROVIDER=mock` runs fully offline with zero secrets for local development and CI.



