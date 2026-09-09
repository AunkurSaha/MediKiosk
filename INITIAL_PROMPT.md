# Initial Claude Code Prompt — MediKiosk

You are the primary implementation agent for **MediKiosk — AI-Powered Pre-Consultation Clinical Intake**, an SIH prototype.

First, read these repository documents completely:

- `CLAUDE.md`
- `docs/prd.md`
- `docs/architecture.md`
- `docs/data-model.md`
- `docs/api-contract.md`
- `docs/design.md`
- `docs/clinical-scope.md`
- `docs/rules.md`
- `docs/testing.md`
- `docs/security-privacy.md`
- `docs/roadmap.md`
- `docs/requirements-traceability.md`
- `docs/decisions.md`
- `docs/memory.md`

Then inspect the repository as it currently exists.

## Product context

MediKiosk prepares a **structured, reviewable draft of patient history and prior-record information before the patient reaches the doctor**.

The intended user flow is:

```text
Language
→ Identification
→ Consent
→ Voice/Touch Interview
→ Adaptive Clinical Questions
→ Continuous Red-Flag Screening
→ Past History
→ Document Upload/Scanning
→ OCR + Medical Extraction
→ Medical Timeline
→ History + Document Fusion
→ Draft Clinical Summary
→ Doctor Review/Edit/Confirm
→ FHIR-ready final record
→ ABDM/HIS integration later
```

There are three interfaces:
1. Patient Kiosk
2. Triage Dashboard
3. Doctor Dashboard

The system is an **intake/documentation aid, not a diagnostic or prescribing system**. The doctor is the final reviewer.

## Stack you must use

- React + Vite + TypeScript + Tailwind CSS
- Python + FastAPI + Pydantic + SQLAlchemy + Alembic
- PostgreSQL
- REST JSON
- WebSocket for triage alerts when that phase is reached
- pytest
- Vitest + React Testing Library
- Docker Compose later for local integration

Do not add extra frameworks merely for sophistication.

## What I want you to do now

Work only on the earliest incomplete roadmap phase.

For a fresh repository, that means **Phase 1: deterministic end-to-end foundation with no external AI dependency**.

Create a clean modular-monolith scaffold and implement this first vertical slice:

### Patient side
- `/kiosk/language`
- `/kiosk/identify`
- `/kiosk/consent`
- `/kiosk/interview`
- `/kiosk/complete`

Support English, Bengali, and Hindi in the UI structure. Initial translations may be local static strings.

For identification, use demo values only:
- optional demo ABHA field;
- patient name;
- hospital token.

Do **not** implement Aadhaar authentication or production ABDM identity.

For consent, persist granular fields:
- voice processing;
- document processing;
- sharing with doctor.

For the initial interview, implement deterministic typed/touch answers for:
- chief complaint;
- onset/duration;
- current medications;
- allergies;
- relevant past medical history.

No LLM is required yet.

### Doctor side
- `/doctor`
- list current intake sessions;
- open one session;
- show patient identification;
- show captured answers in a structured layout;
- allow doctor to create/edit a reviewed summary;
- allow doctor to confirm it.

Preserve both the draft/review content and confirmation metadata.

### Backend
Create:
- health endpoint;
- patient/session endpoints;
- consent endpoint;
- interview-answer endpoints;
- doctor session-detail endpoint;
- summary update/confirm endpoints.

Use Pydantic response/request models and SQLAlchemy persistence.

### Database
Create initial models/migrations for:
- patients;
- users (minimal role-ready model);
- sessions;
- consents;
- interview_answers;
- clinical_summaries;
- audit_logs.

Use PostgreSQL in the intended deployment. If developer convenience requires SQLite for a fast unit-test profile, isolate that to tests and do not change the production database decision.

### Engineering
Also create:
- `.env.example`;
- backend dependency file;
- frontend package setup;
- lint/type/test scripts;
- basic error handling;
- seed/demo script or documented way to create a demo doctor;
- minimal README setup instructions if missing.

## Important constraints

- Do not implement diagnosis, treatment advice, or prescribing.
- Do not fake working BHASHINI, ABDM, OCR, or LLM integration.
- If an external dependency is not configured, use a clearly labelled adapter/mock only in phases that require it.
- No secrets in code.
- Do not store voice recordings yet.
- No document OCR yet.
- No microservices.
- No Redis yet.
- Do not jump ahead to Phase 2+ unless Phase 1 is complete and tested.

## Required working style

1. Inspect before editing.
2. Keep changes small and coherent.
3. Use typed contracts end to end.
4. Write tests with the implementation.
5. Run relevant checks yourself.
6. Fix failures before declaring completion.
7. Update `docs/decisions.md` if you make a real architectural decision.
8. Update `docs/memory.md` only with durable project facts or unresolved next-step context—not a verbose activity log.
9. At the end, give me:
   - what you built;
   - files created/changed;
   - commands to run it;
   - tests/checks run and their results;
   - any blockers;
   - the exact recommended next task.

Begin by reading the docs and repository. Then implement the earliest incomplete roadmap phase without asking me to reconfirm decisions that are already documented.
