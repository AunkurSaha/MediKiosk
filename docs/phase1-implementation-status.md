> Historical milestone report. Current acceptance and known limitations are governed by [stabilization status](stabilization-implementation-status.md). Old test counts and recommendations do not authorize new phase work.

Historical Phase 1 acceptance report. For current scope, see [implementation-status.md](implementation-status.md).

# Implementation status — 2026-09-09

## Current milestone

Phase 1 is implemented and verified as a local synthetic-data demonstration:

Language → identification → consent → five deterministic history answers → PostgreSQL → doctor review/edit/confirm → audit trail.

The next roadmap task is Phase 2, the deterministic adaptive interview engine. No external AI keys are needed yet.

## Delivered

- Responsive patient flow at `/kiosk/language`, `/kiosk/identify`, `/kiosk/consent`, `/kiosk/interview`, and `/kiosk/complete`.
- Static English, Bengali, and Hindi patient forms/questions.
- Atomic, retry-safe patient/session creation using a retained client UUID.
- Consent enforced on the backend, including rejection of direct API bypass.
- Five required history fields, incremental saving, explicit unknown answers, refresh/resume, and kiosk reset.
- Corrections preserve previous patient wording; reads return the latest answers in stable question order.
- Doctor session list/detail with patient names, tokens, exact patient answers, and source labels.
- A deterministic draft from saved structured answers, clearly identified as not AI-generated.
- Reviewed summary revisions, optimistic version checks, server-owned reviewer/confirmation metadata, immutable confirmed records, and key audit events.
- Repaired Pydantic schemas, consistent errors, bounded text fields, and explicit allowed workflow states.
- PostgreSQL 18.6 running locally with an app role and separate test database.
- Initial migration plus an additive audit/integrity migration; schema matches model metadata.
- Tailwind configured; ESLint, Prettier, TypeScript, Vitest, React Testing Library, pytest, Ruff, and Playwright checks available.
- Start/stop scripts and exact environment/setup documentation. Existing SQLite files and older Python environment were preserved.

## Evidence

| Check | Result |
|---|---|
| Frontend build / TypeScript | Passed |
| ESLint | Passed, zero warnings |
| Prettier | Passed |
| Frontend component tests | 10 passed |
| Backend HTTP/workflow suite, PostgreSQL | 19 passed |
| Backend HTTP/workflow suite, isolated SQLite test profile | 19 passed |
| Ruff | Passed |
| PostgreSQL migrations on empty app/test databases | Passed |
| Alembic schema comparison | No pending model/schema changes |
| Headless browser tests | 2 passed |
| Real backend + PostgreSQL restart | Passed; new process IDs, unchanged answers/draft/review/confirmation |

The browser test creates a clearly named synthetic patient, reloads midway through intake, saves every answer, clears kiosk identity, opens the doctor workspace, edits/confirms, and reloads the final record. A second browser test checks Bengali identification on a 390-pixel mobile viewport. Desktop and mobile screenshots were visually inspected.

Test artifacts live under ignored `.runtime/`, including screenshots, Playwright failure traces, and the synthetic record reference used by the restart checker. Browser tests intentionally leave synthetic records available in the local demo database.

The installed Starlette test client emits an upstream AnyIO alias deprecation warning. It does not affect test results; application warnings remain errors in pytest.

## Deliberate limits

- This is a loopback-only demo with explicit demo-doctor access, not production authentication.
- Public session access uses unguessable UUIDs as a local convenience. Implement staff authentication and patient access tokens before exposing real data or deploying beyond the demo environment.
- Voice and document consent stay false because those processing paths are not implemented.
- Triage explicitly says safety monitoring is unavailable.
- Phase 2 complaint JSON files remain draft, inactive material. Their translations and clinical content are not validated. Active Phase 1 forms do not import them.
- No normalization, voice provider, OCR, red flags, timeline, FHIR, or ABDM integration is claimed.
- Existing SQLite demo data was preserved, not migrated into the new PostgreSQL database.
- Docker packaging and production hosting remain deferred.
- The CI workflow is supplied for future repository use; remote CI execution has not been verified here.

## Recommended next task

Implement Phase 2 from a single authoritative configuration under `ai/complaint_flows/`:

1. Define and validate one complaint-flow schema.
2. Review translations and prototype clinical wording.
3. Build deterministic required-field and branch selection on the backend.
4. Support five complaint families and a separately labeled AYUSH demo.
5. Test positive, negative, missing-answer, and back/edit paths.
6. Preserve the existing consent, incremental persistence, source provenance, and doctor-confirmation boundaries.
