# Implementation Plan for Claude Code — Initial Sprint

This is the practical execution checklist for a fresh repository.

## Step 1 — Scaffold

Create:
- root `.gitignore`;
- `.env.example`;
- `frontend/`;
- `backend/`;
- backend config/database wiring;
- Alembic;
- initial tests.

Do not remove the provided docs.

## Step 2 — Backend foundation

Implement:
- FastAPI app factory/main;
- config;
- DB session;
- health route;
- consistent error handling.

Initial DB models:
- User;
- Patient;
- IntakeSession;
- Consent;
- InterviewAnswer;
- ClinicalSummary;
- AuditLog.

## Step 3 — Phase 1 APIs

Implement documented endpoints from `api-contract.md`.

Keep code thin:
- API layer handles HTTP;
- service layer handles workflow;
- DB layer persists.

## Step 4 — Frontend foundation

Implement routing:
- `/kiosk/language`
- `/kiosk/identify`
- `/kiosk/consent`
- `/kiosk/interview`
- `/kiosk/complete`
- `/doctor`
- `/doctor/sessions/:sessionId`
- `/triage` placeholder allowed until alert phase.

Add localization resources for English/Bengali/Hindi.

## Step 5 — Vertical slice

Prove:

```text
patient → session → consent → answers → database
                                     ↓
                              doctor dashboard
                                     ↓
                            review → confirmation
```

## Step 6 — Tests and polish

- API tests;
- service tests;
- frontend component tests;
- build/lint;
- meaningful empty/error/loading states;
- seed demo data if useful.

## Step 7 — Document the result

Update:
- README setup;
- `docs/setup.md`;
- `docs/memory.md` if the implementation established durable facts;
- `docs/decisions.md` only for genuine decisions.

## Do not do in initial sprint

- live LLM;
- live BHASHINI;
- OCR;
- document upload;
- red flags;
- WebSockets;
- FHIR;
- ABDM;
- Redis;
- microservices.

The goal is a boring, stable spine that later AI features can attach to.
