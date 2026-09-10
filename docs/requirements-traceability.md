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
| Timeline, discrepancies, AI summary, FHIR, ABDM | No accepted implementation | Deferred; no Phase 7 work authorized |
