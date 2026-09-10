# Requirements traceability — stabilization

Evidence must demonstrate behavior; a test count alone does not accept a feature. Current acceptance gates and limits are in [stabilization status](stabilization-implementation-status.md).

| Requirement | Implementation / regression evidence | Limit |
|---|---|---|
| Phase 1 consent, identity, answer persistence and doctor confirmation | test_workflow.py; intake.spec.ts | Local UUID patient access and explicit demo doctor, not production authentication |
| Deterministic adaptive interview, edits, resume, AYUSH isolation | test_adaptive.py; adaptive.spec.ts; restart.spec.ts | Unvalidated clinical wording/translations |
| Optional normalization with raw source preservation | test_normalization.py; normalization.spec.ts | Exact offline vocabulary; no broad clinical understanding |
| NVIDIA boundary, negation, uncertainty and failure fallback | test_nvidia_normalization.py; retained live evaluation | Live evidence 3/26 domain passes, 23 timeouts; not reliable acceptance |
| Staff document/triage authorization and server attribution | test_stabilization_security.py; stabilization.spec.ts | Existing demo identity only |
| WebSocket authorization and actual delivery | staff_tickets.py; triage_notifier.py; stabilization.spec.ts open-dashboard scenario | Process-local sockets; no guaranteed human notification |
| Red-flag source context, polarity, explanation fidelity | test_stabilization_alerts.py; multilingual stabilization browser scenarios | Existing unvalidated thresholds; unknown wording requires review |
| Alert lifecycle and counters | test_red_flags.py; test_stabilization_alerts.py; open-dashboard browser scenario | No distributed durable delivery queue |
| Document type/content/path/failure handling | test_stabilization_documents.py; test_documents.py; stabilization.spec.ts | No crash-atomic filesystem/SQL transaction |
| Lab API/UI schema and missing flags | StructuredDocument; DocumentViewer; document API/browser regressions | No invented interpretation of missing flags |
| Explicit mock OCR versus arbitrary uploads | content-addressed ai/document_fixtures; document regressions | Real OCR not implemented |
| Voice consent/candidate/source provenance | test_stabilization_voice.py; test_speech.py; speech.spec.ts | Signed pending candidates expire/restart-invalidated; no permanent audio storage |
| Multipart cleanup/cancellation | spooled-upload API regressions; speech.test.tsx | Temporary disk spooling occurs; abrupt termination cleanup not guaranteed |
| BHASHINI adapter/configuration/audio/deadline | test_bhashini_speech.py; test_stabilization_bhashini.py | Mocked transport only; native browser audio not live-accepted |
| Schema consistency and upgrade preservation | verify-stabilization-migrations.py; Alembic check | Application upgrades only; downgrades isolated to disposable test schemas |
| Restart preservation | verify-restart.ps1 and stabilization references | PostgreSQL control currently blocked by Windows Application Control |
| Source-linked medical facts and fact review history | medical_facts.py; medical_fact_revisions; test_phase7_complete.py; phase7.test.tsx | Synthetic typed fixtures only; no real OCR or clinical validation |
| Deterministic timeline and explicit unknown dates | timeline.py; timeline API/UI; backend and browser ordering/unknown-date tests | Computed only from explicit dates; generic timeline table remains unused |
| Conservative discrepancies | discrepancies.py; discrepancy API/UI; medication/allergy/lab unit and browser tests | Incomparable evidence emits nothing; output always requires clinician review |
| Deterministic draft summary, evidence attribution, doctor review, revision history, and confirmed locking | ClinicalSummaryService; summary_revisions; test_phase8_summary.py; phase8.test.tsx | Deterministic template synthesis only; no LLM diagnosis/prescriptions/invented dates |
| FHIR export, ABDM | No Phase 10+ implementation | Deferred and not authorized |


## Phase 7 completion evidence

| Scope | Implementation | Evidence / remaining gap |
|---|---|---|
| Persist document medication/lab facts | medical_extractor plus medication_fact/lab_fact tables | Seven backend repair regressions; two browser upload + direct PostgreSQL + doctor display checks |
| Preserve source and unknown flags | Raw extraction copied, extraction FK retained, missing flags/dates/locations unknown | Retry/source/logging, missing-flag and failure-isolation regressions |
| Timeline/discrepancies | Computed timeline service plus deterministic comparison service and doctor sections | Known/equal/unknown ordering, no invented dates/duplicates, explicit comparable evidence, stable IDs, source A/B, component and browser coverage |
| Fact review | Staff-only typed PATCH routes and additive revisions | Authorization, forgery rejection, optimistic conflict, original/current separation, locked session and server reviewer coverage |
| Migration integrity | Forward index repair plus additive review-history migration | PostgreSQL comparison/upgrades/fingerprints/downgrade-reupgrade; Phase 7 SQLite schema and preserved scaffold-row regression |


## Phase 8 completion evidence

| Scope | Implementation | Evidence / remaining gap |
|---|---|---|
| Deterministic clinical summary drafting | `ClinicalSummaryService` synthesizing intake answers, normalized facts, medication/lab medical facts, timeline, discrepancies, and red flags | 10 fixed sections, all 5 complaint families tested, AYUSH disclaimer, no LLM or invented facts |
| Explicit unknown information preservation | `unknown_unreported` section capturing explicitly missing or unassessed clinical domains | Unknowns retained, no hallucinated defaults |
| Source evidence attribution | `EvidenceReference` linking every summary statement to source type, source ID, and raw source text | `GET /api/doctor/sessions/{id}/summary/evidence`, component and backend attribution tests |
| 4-stage lifecycle & immutable draft | `clinical_summaries` (`generated_text`, `reviewed_text`, `confirmed_text`), optimistic `draft_version` | Doctor edits never mutate `generated_text`; replacement confirmation modal on regenerate |
| Append-only revision history | `summary_revisions` capturing `revision_type`, `actor_type` (DOCTOR vs SYSTEM), `review_notes`, snapshots | Complete chronological audit trail, server-stamped actor identity, optimistic locking |
| Clinician confirmation locking | `POST /api/doctor/sessions/{id}/summary/confirm` locking summary with `confirmed_by`, `confirmed_at` | Subsequent PUT/regenerate rejected with 409 `CONFIRMED_IMMUTABLE`; audit log emitted |
| Doctor Summary Workspace UI | `SummaryWorkspace` with Editor, Evidence attribution viewer, Revision feed, and Read-only confirmed view | 6 frontend component tests (`phase8.test.tsx`), lint, and build verified |

