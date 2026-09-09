# Implementation Roadmap — MediKiosk

Do not jump phases merely because later phases are more impressive.

Each phase should leave the repository runnable.

Current status (2026-09-09): Phases 1, 2, 3A, 3B, 4A, 4B, and 5 are implemented and verified for the local synthetic-data demo.
See [implementation-status.md](implementation-status.md), [phase4b-implementation-status.md](phase4b-implementation-status.md), and [phase5-implementation-status.md](phase5-implementation-status.md) for evidence and limits.
Phase 4B completed the real BHASHINI (ULCA) speech provider adapter for ASR and TTS with pipeline discovery, in-memory caching, direct inference support, and failure resistance. The next milestone is Phase 6 (Document Ingestion + OCR Pipeline).

## Phase 0 — Repository context

Status: starter documents supplied.

Deliver:
- repo/docs initialized;
- environment conventions;
- gitignore;
- basic setup documentation.

## Phase 1 — Deterministic end-to-end foundation

Goal:

```text
Patient enters
→ creates session
→ grants consent
→ answers deterministic questions
→ data stored
→ doctor sees data
→ doctor edits/confirms review
```

Deliver:
- React app;
- FastAPI app;
- PostgreSQL;
- migrations;
- patient/doctor route skeleton;
- language/identification/consent/interview/complete UI;
- doctor session list/detail;
- summary edit/confirm;
- audit events for key actions;
- tests.

No AI, OCR, voice, red flags, FHIR, or ABDM required.

Exit criteria:
- fresh setup works;
- data survives backend restart with database;
- doctor can see exactly what patient entered;
- confirmation state persists;
- checks pass.

## Phase 2 — Structured adaptive interview

Status: implemented; deterministic API, UI, PostgreSQL, browser and restart checks are documented in the implementation status.

Add:
- explicit deterministic complaint selection (normalization deferred to Phase 3);
- question-flow config;
- five complaint families;
- required field completion;
- branch logic;
- structured clinical history builder;
- separate AYUSH demonstration question configuration.

Store configs in `ai/complaint_flows/`.

Exit criteria:
- deterministic tests prove next-question behavior;
- no uncontrolled LLM interview.

## Phase 3A — Provider-neutral normalization

Status: complete and verified with deterministic mock, strict schemas, explicit field eligibility, failure fallback, durable provenance, source invalidation, UI and migration/restart tests. No external credentials or API calls.

## Phase 3B — NVIDIA NIM real clinical normalization provider

Status: complete and verified. Integrates NVIDIA Build / NIM hosted inference (`google/gemma-4-31b-it`) behind the provider-neutral boundary. Schema 1.1 provides explicit negation/polarity, uncertainty, null confidence, and strict evidence matching. Failures cleanly degrade to explicit unavailable states while raw patient answers commit safely. Offline mock remains default; live calls require opt-in configuration. See [Phase 3B report](phase3b-implementation-status.md).


## Phase 4A — Provider-neutral voice input + TTS architecture

Status: complete and verified. Delivers provider-neutral speech boundary (`SpeechProvider` protocol, `MockSpeechProvider`), browser MediaRecorder capture, zero raw audio retention, ephemeral temp file processing, strict consent enforcement (`voice_processing: true`), candidate transcript confirmation UI with edit and retry, provenance tracking (`source: 'voice'`), and localized question TTS synthesis. Regressions and 12 E2E scenarios pass across SQLite and PostgreSQL. See [Phase 4A report](phase4a-implementation-status.md).

## Phase 4B — Real speech provider integration (BHASHINI / AI4Bharat)

Status: complete and verified; see [phase4b-implementation-status.md](phase4b-implementation-status.md).

Implemented:
- `BhashiniSpeechProvider` adapter implementing `SpeechProvider` protocol (`backend/app/services/bhashini_speech.py`);
- ULCA pipeline discovery (`/ulca/apis/v0/model/getModelsPipeline`) with 1-hour in-memory cache and direct compute callback invocation;
- Pre-configured direct inference mode support (`BHASHINI_INFERENCE_URL`, `BHASHINI_INFERENCE_API_KEY`);
- MIME-to-format translation (`audio/webm` -> `"webm"`, `audio/wav` -> `"wav"`, `audio/ogg` -> `"ogg"`);
- Candidate confirmation gate strictly preserved: ASR output requires explicit patient action before persisting;
- Zero raw audio retention: ephemeral in-memory audio buffers immediately freed;
- Localized TTS synthesis for pinned complaint flow questions in English, Bengali, and Hindi;
- Operator evaluation script (`scripts/evaluate-bhashini-speech.py`);
- Full test suite: 20 unit/mock integration tests, all 270 backend tests passing across SQLite and PostgreSQL.


## Phase 5 — Red-flag engine + triage
Status: Implemented and verified; see [phase5-implementation-status.md](phase5-implementation-status.md).

Implemented:
- Deterministic versioned rules (`ai/safety_rules/red_flags_v1.json`, 11 rules across 5 complaint families: Chest Pain, Cough/Breathlessness, Fever, Headache, Abdominal Pain). Zero LLM safety decision-making.
- Additive PostgreSQL alert persistence (`backend/alembic/versions/f54c306d1e24_red_flag_alerts.py`) with `uq_session_rule_alert` unique constraint and automatic re-arming/resolution.
- Triggering facts explanation preserving field, value, raw_value, and question identity.
- Staff Triage Dashboard (`/triage`) with live counters, priority/status filters, and multilingual support (EN/BN/HI).
- Live WebSocket push (`/api/triage/ws`) broadcasting `alert_created` and `alert_acknowledged` events.
- Audit-logged staff acknowledgement with staff name/ID and action note.
- Calm, non-diagnostic patient advisory on Kiosk UI (`docs/design.md` Section 8).
- Physician visibility in Doctor Workspace (`/doctor/sessions/:id`).
- Full test suite: 18 red-flag unit/integration tests, 5 vitest triage component tests, Playwright E2E emergency journey, and migration/restart verification.

## Phase 6 — Document ingestion + OCR

Add:
- upload;
- object storage;
- media validation;
- OpenCV preprocessing;
- PaddleOCR adapter;
- document classification;
- confidence/provenance;
- original document viewer.

Start with printed lab reports, then printed prescriptions.

## Phase 7 — Medical extraction + timeline + discrepancies

Add:
- medication/lab extraction;
- regex + structured AI extraction where useful;
- normalized facts;
- chronological timeline;
- patient-vs-document discrepancy detection;
- verification status.

## Phase 8 — Draft summary

Add:
- summary provider;
- summary from structured facts;
- explicit unknowns;
- generated draft preservation;
- doctor editor improvements.

## Phase 9 — Doctor verification hardening

Add:
- field-level verification where useful;
- versioning/revisions;
- better audit;
- document/source cross-reference.

## Phase 10 — FHIR export

Add:
- mappings;
- FHIR validation;
- export screen/API;
- tests against representative records.

Do not block internal implementation on FHIR schema too early.

## Phase 11 — ABDM / HIS demonstration

Add only after core flow works:
- ABDM sandbox connector where credentials/onboarding allow;
- otherwise a clearly labeled mock/sandbox integration demonstration;
- architecture showing HIS interoperability.

## Phase 12 — Demo polish

Add:
- seeded showcase patient;
- Bengali chest-pain scenario;
- realistic loading states;
- kiosk full-screen polish;
- judge-friendly triage alert;
- timeline visuals;
- FHIR export preview;
- reset demo command.

## Priority rule

If a later feature is blocked, preserve the complete flow with a transparent mock rather than pretending the integration works.
