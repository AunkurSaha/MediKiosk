# Project Memory — MediKiosk

This file is durable project context for AI coding agents.

Latest audit: [current-project-review-2026-09-09.md](current-project-review-2026-09-09.md) supersedes the completion assumptions below. Phase 6 upload/mock-OCR code and tables are present, but staff authorization, alert delivery/interpretation, document verification/display and speech acceptance need stabilization. Fresh checks: 280 backend tests per database, 52 frontend tests, 12/14 browser tests; Alembic comparison, Ruff and Prettier are not clean. Do not advance phases based solely on the older summaries.

Keep it concise. Update only when a fact is likely to matter across future sessions.

## Product identity

- Project: **MediKiosk**
- Purpose: AI-assisted pre-consultation clinical intake.
- Context: SIH prototype.
- Core principle: prepare structured information before consultation; doctor remains final reviewer.
- Not a diagnostic/prescribing system.

## Chosen stack

- React + Vite + TypeScript + Tailwind CSS
- Python + FastAPI + Pydantic + SQLAlchemy + Alembic
- PostgreSQL
- MinIO/S3-compatible object storage when document pipeline is implemented
- OpenCV + PaddleOCR adapter for printed OCR
- speech provider behind adapter; BHASHINI/AI4Bharat are intended options
- provider-agnostic LLM adapter
- REST + WebSocket alerts
- FHIR adapter; ABDM sandbox later
- Docker Compose for integrated local run

## Repository strategy

- Modular monolith.
- One frontend with route namespaces for kiosk, doctor, and triage.
- One backend with internal service modules.
- Structured clinical data is canonical.
- External AI/provider results are unverified until appropriate validation/human verification.

## Initial complaint scope

Implemented as prototype/unvalidated adaptive flows:
- chest pain;
- abdominal pain;
- fever;
- headache;
- cough/breathlessness.

## Initial language scope

- English
- Bengali
- Hindi

Architecture should remain expandable to additional Indian languages.

## Build strategy

Current milestone: Phases 1, 2, 3A, 3B, 4A, and 5 implemented and verified locally (2026-09-09).
- Start with `scripts/start-dev.ps1`; app port 5175, backend 8010, PostgreSQL 55432.
- Use `backend/.venv`, not the preserved older `backend/venv`.
- PostgreSQL lives under ignored `.runtime/`; configuration is in ignored `backend/.env`.
- Real staff auth is deferred; explicit demo-doctor access is gated by `DEMO_MODE` and is disabled in production.
- Patient/session creation is atomic. API is under `/api`; see the updated contract.
- Sole flow source: `ai/complaint_flows/`; Pydantic validates configuration at startup. Backend owns branching; React only renders returned questions.
- Each interview pins a flow snapshot/version and cursor/revision. Durable request receipts prevent delayed retries undoing corrections.
- Corrections append rows. Inactive branch history is retained but excluded from current facts; reactivation restores latest answers/provenance.
- Five standard flows plus a separate AYUSH demonstration are active. Wording/translations remain clinically unvalidated.
- Typed ClinicalHistory is computed from active answers and snapshotted in existing summary JSON at completion. Legacy Phase 1 answers remain compatible.
- Summary drafts are deterministic. Doctor edits preserve drafts and revisions; confirmed records are read-only.
- Phase 3A: normalization_provider.py defines the async interface and mock. Explicit short-text field eligibility lives in normalization_policy.py; typed answers and AYUSH bypass it.
- Normalization results are immutable per source answer, including unknown/unrecognized/provider failures. Savepoints isolate enrichment storage failures. Active history adds normalization without replacing reported text or driving branches.
- Phase 3B: integrated NVIDIA Build / NVIDIA NIM (`google/gemma-4-31b-it`) hosted inference via `NvidiaClinicalNormalizationProvider`. Schema 1.1 requires explicit polarity (`present`/`absent`), certainty (`certain`/`uncertain`), `confidence: null`, and exact evidence substring. Secrets are protected in `SecretStr`, excluded from serialization/repr/logs.
- If NVIDIA is unavailable or times out, raw answers remain committed and normalization status records explicit `unavailable` failure state. No silent fallback to mock.
- Phase 4A: speech_provider.py defines the async `SpeechProvider` interface and deterministic `MockSpeechProvider`. Ephemeral audio processing with zero raw audio retention (context managed temp files unlinked in `finally`). Strict voice consent enforcement (`voice_processing: true`). Candidate confirmation workflow: ASR transcript is unconfirmed candidate; patient explicitly confirms (persists as `source: 'voice'`) or edits (persists as `source: 'typed'`). Downstream clinical normalization runs only after explicit answer confirmation. Question TTS synthesizes strictly localized text from pinned flow snapshot; no clinical history or patient answers sent to TTS.
- Phase 4B: Bhashini (ULCA) real speech provider integration (`backend/app/services/bhashini_speech.py`). Connects live ASR and TTS via ULCA pipeline discovery (`/ulca/apis/v0/model/getModelsPipeline`) with 1-hour in-memory cache and direct compute endpoint support (`BHASHINI_INFERENCE_URL`). Zero raw audio retention; ephemeral in-memory processing. Candidate confirmation workflow strictly preserved. Localized question TTS across English, Bengali, Hindi. Graceful degradation on timeout, rate limiting, or upstream errors into explicit `unavailable` results without disrupting interview. Diagnostic script `scripts/evaluate-bhashini-speech.py`.
- Phase 5: Deterministic safety screening engine (`backend/app/services/red_flags.py`) evaluating structured active facts and normalized concepts against versioned catalog (`ai/safety_rules/red_flags_v1.json`, 11 rules across 5 complaint families). Zero LLM safety decision-making. Additive `alerts` table (`backend/alembic/versions/f54c306d1e24_red_flag_alerts.py`) with `uq_session_rule_alert` unique constraint ensuring idempotency and automatic answer reconciliation. Real-time WebSocket feed (`/api/triage/ws`) pushing `alert_created` and `alert_acknowledged` events. Staff Triage Dashboard (`/triage`) with live counters, priority/status filters, and staff acknowledgement form with audit logging. Calm, non-diagnostic patient advisory on Kiosk UI (`docs/design.md` Section 8). Physician visibility in Doctor Workspace (`/doctor/sessions/:id`).
- Offline tests use mock by default. Next milestone: Phase 6 (Document Ingestion + OCR Pipeline).
- See `docs/implementation-status.md`, `docs/phase3b-implementation-status.md`, `docs/phase4a-implementation-status.md`, `docs/phase4b-implementation-status.md`, and `docs/phase5-implementation-status.md` for current acceptance evidence.

Implement in phases:
1. deterministic end-to-end CRUD vertical slice;
2. structured adaptive interview;
3. language understanding/normalization;
4. voice;
5. deterministic red flags;
6. documents/OCR/extraction;
7. timeline/discrepancies;
8. summary;
9. doctor verification hardening;
10. FHIR;
11. ABDM/demo integration.

## Durable safety decisions

- LLM does not solely control medical interview.
- LLM does not solely detect red flags.
- OCR confidence/provenance is preserved.
- AI draft and doctor-confirmed summary remain distinguishable.
- Patient statements and prior documents may conflict; flag for verification rather than choosing silently.

## Known intentional deferrals

- real Aadhaar authentication;
- production ABHA authentication/onboarding;
- production HIS;
- national-scale infrastructure;
- Redis;
- microservices;
- handwritten-prescription perfection;
- broad diagnostic coverage.

## How to update this file

Add only:
- confirmed architecture choices;
- important product scope changes;
- major unresolved blocker that next session must know;
- a changed project phase.

Do not turn this into a timestamped work log. Use git history/issues for that.
