# AGENTS.md — MediKiosk Repository Instructions

You are working on **MediKiosk**, an SIH prototype for AI-assisted pre-consultation clinical intake.

Treat this file as the highest-level repository guidance. Read the referenced documents before making architectural changes.

## Mission

Build a working prototype that helps collect and structure patient history and past medical records **before the doctor consultation**, while preserving human clinical control.

The product must demonstrate:

- multilingual-friendly patient intake;
- voice and touch input paths;
- structured adaptive questioning;
- continuous red-flag screening;
- document upload/OCR/extraction;
- longitudinal medical timeline;
- physician-ready draft summary;
- doctor review/edit/confirmation;
- FHIR-ready export architecture.

## Non-negotiable clinical boundary

MediKiosk is **not an autonomous diagnostic system**.

Never implement UI copy or backend behavior that:
- declares a diagnosis as fact;
- prescribes treatment;
- tells the patient a medication to start/stop/change;
- suppresses or overrides clinician review;
- converts uncertain OCR/AI extraction into verified clinical fact.

Use phrases such as:
- “Potential emergency symptoms detected.”
- “Immediate clinical assessment recommended.”
- “Needs verification.”
- “Patient reported…”
- “Previous document indicates…”

Do not use:
- “You have…”
- “Diagnosis: …”
- “Take this medicine…”
- “No doctor review required.”

## Technology constraints

Use:

- **Frontend:** React + Vite + TypeScript + Tailwind CSS
- **Backend:** Python + FastAPI
- **Schemas:** Pydantic
- **ORM:** SQLAlchemy
- **Migrations:** Alembic
- **Database:** PostgreSQL
- **Testing:** pytest + Vitest + React Testing Library
- **API style:** REST JSON; WebSocket only for real-time alerts
- **Formatting/lint:** Ruff for Python; ESLint/Prettier for TypeScript

Do not introduce another framework/language unless a documented decision is added to `docs/decisions.md`.

Do not introduce Kubernetes, Kafka, blockchain, MongoDB, Java/Spring, Flutter, or microservices for the MVP.

## Repository shape

Target structure:

```text
medikiosk/
├── frontend/
│   └── src/
│       ├── app/
│       ├── routes/
│       │   ├── kiosk/
│       │   ├── doctor/
│       │   └── triage/
│       ├── components/
│       ├── features/
│       ├── api/
│       ├── types/
│       └── i18n/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── main.py
│   ├── tests/
│   └── alembic/
├── ai/
│   ├── complaint_flows/
│   ├── red_flag_rules/
│   ├── ontology/
│   └── prompts/
├── docs/
├── docker/
├── docker-compose.yml
├── .env.example
└── README.md
```

Keep the system as a **modular monolith** for the prototype. Services are code boundaries, not independently deployed microservices.

## Clinical scope

Read `docs/clinical-scope.md` before implementing adaptive clinical flows. The prototype includes:
- five initial complaint families;
- standard structured history sections;
- one separately configured AYUSH demonstration pathway;
- continuous deterministic safety screening.

Do not invent clinical rule content casually. Treat unreviewed rules as prototype/demo logic.

## Source of truth

The source of truth is **structured clinical data**, not generated prose and not the raw chat transcript.

Preferred pipeline:

```text
unstructured input
→ normalized structured data
→ deterministic validation/safety checks
→ persistence
→ generated draft summary
→ doctor review/edit
→ confirmed record
```

## AI boundaries

LLMs may help with:
- natural-language understanding;
- multilingual normalization;
- extraction into defined schemas;
- summarization from validated structured data.

LLMs must not be the sole authority for:
- red-flag detection;
- required interview-field completion;
- consent;
- authentication/authorization;
- audit records;
- final clinical verification.

All AI outputs must be schema-validated and capable of carrying confidence/provenance metadata.

## Red flags

Red flags are deterministic, versioned rules stored in `ai/red_flag_rules/`.

Every alert must include:
- severity/priority;
- rule ID;
- human-readable reason;
- triggering structured facts;
- timestamp;
- acknowledgement state.

Never show an inferred diagnosis as the alert reason.

## OCR and documents

Every extraction must retain provenance:
- source document ID;
- source page/region when available;
- extractor/provider;
- confidence;
- verification state.

Low-confidence text must remain visibly unverified.

Do not overwrite raw extraction with a corrected-looking value without preserving the original.

## Doctor verification

Keep:
- generated draft;
- clinician-edited final version;
- verifier identity;
- verification timestamp;
- revision/version history when applicable.

The doctor’s confirmed record must not silently replace the AI draft in audit history.

## Coding behavior

Before coding:
1. read the relevant docs;
2. inspect existing code;
3. state assumptions only when needed;
4. make the smallest coherent change;
5. add/update tests;
6. update docs if behavior/contracts changed.

When implementation and documentation disagree:
- do not silently choose one;
- prefer the explicit ADR/decision record;
- otherwise update both as part of the same change.

## Definition of done

A task is not done until:
- code runs;
- lint/type checks pass for touched code;
- relevant tests pass;
- errors are handled;
- no secrets are committed;
- user-visible state includes loading/error/success handling where relevant;
- API contracts remain typed;
- clinically sensitive data retains source/verification status;
- docs are updated when contracts/architecture changed.

## Start here

Read `docs/roadmap.md`. For a new repository, implement **Phase 1 only** unless the user explicitly asks to move further.
