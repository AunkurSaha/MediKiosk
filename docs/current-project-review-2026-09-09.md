# MediKiosk current project review — 2026-09-09

The project is a substantial working local prototype with a sound intake foundation, but the latest “fully verified” and “ready for production” claims are not supported by the current implementation. Code now extends into Phase 6, beyond the Phase 5 milestone named in the summary documents. The immediate next milestone should be stabilization and truthful acceptance evidence.

This review inspected current source, documentation, configuration presence, database schema, existing tests, isolated adversarial probes and the browser. Application features were not rewritten during this review. Findings below remain open. Synthetic records were used throughout.

**Where the project stands**

| Area | Actual status |
|---|---|
| Phase 1: identity, consent, persistence, doctor summary review | Implemented; existing API and browser regressions pass. Doctor-summary confirmation remains distinct from machine output. |
| Phase 2: deterministic adaptive interview | Implemented; five complaint families, separate AYUSH flow, pinned configuration, corrections and resume remain present and tested. |
| Phase 3A: offline normalization | Implemented; explicit eligible fields, strict allowlist, source history and unverified machine representation remain present. |
| Phase 3B: NVIDIA normalization | Adapter implemented and offline-tested. Retained live evaluation has 3/26 domain passes and 23 timeouts; a separate 15-second smoke run has 0/5 passes. This is not reliable live acceptance. |
| Phase 4A: voice candidate UI and question playback | Implemented with mock speech; five existing speech browser tests pass. Backend consent/provenance and audio-handling gaps remain. |
| Phase 4B: BHASHINI | Adapter and mocked tests exist. Local BHASHINI API key, user ID and inference key are absent; live ASR/TTS is not demonstrated by the supplied evidence. |
| Phase 5: safety screening and triage | Rules, persistence, API, dashboard and WebSocket connection exist. Notification, access-control, interpretation and lifecycle defects prevent acceptance as completed safety screening. |
| Phase 6: documents/OCR | Uploads, storage, tables, parser and doctor UI are implemented as a scaffold. OCR supports only mock/disabled; it does not read real document content. Verification and lab display have material defects. |
| Later roadmap | No complete timeline/discrepancy system, AI summary generation, FHIR/ABDM integration, production identity/security or deployment acceptance. |

**Fresh verification**

| Check | Observed result |
|---|---|
| Backend SQLite tests | 280 passed; one upstream deprecation warning |
| Backend PostgreSQL tests | 280 passed; the combined helper subsequently fails Ruff |
| Frontend component tests | 52 passed |
| TypeScript and production build | Passed |
| ESLint | Passed |
| Existing Playwright suite, explicitly mock backend | 12 passed, 2 failed |
| Ruff | One import-order error in `a61e405d2e31_document_ingestion_ocr.py` |
| Prettier | Fails on 12 files |
| Current app Alembic comparison | Fails: `alerts.created_at` nullability differs between ORM and migration |
| Additional isolated defect probes | 17 reproductions confirmed; these assert the observed defects and are not acceptance tests |
| Document browser probe | Four stored lab observations; zero rendered lab tables |
| Configured NVIDIA key value scan | Zero matches across 202 checked source/document/log files; this is not a comprehensive security certification |

The two triage browser tests wait for a nonexistent exact “Start intake” button at consent. They fail before evaluating the promised triage journey. Passing unit counts therefore must not be described as completed triage E2E coverage. No document acceptance browser suite is present; the review added only an isolated diagnostic.

PostgreSQL is at revision `a61e405d2e31` and contains the original tables plus `normalization_results`, `alerts`, `documents` and `document_extractions`. New tables existing is distinct from a clean schema comparison. A new full stop/restart acceptance run was not performed during this review, and prior restart claims should not be extended automatically to Phase 6.

**Priority 1 — staff access and clinical verification**

1. **Document verification trusts any caller and a caller-supplied clinician name.** [documents.py](../backend/app/api/v1/documents.py:73) has no existing doctor dependency; [verify_extraction](../backend/app/services/document_service.py:162) neither authenticates a reviewer nor checks session confirmation. The isolated API probe verified and then rejected an extraction without a doctor header after marking its session confirmed. Reuse the existing server-owned doctor identity, define confirmation/amendment rules, and preserve verification revisions instead of overwriting the same fields.

2. **Triage patient information and acknowledgement are unauthenticated.** [triage.py](../backend/app/api/v1/triage.py:45) exposes patient names, tokens and triggering clinical text; acknowledgement accepts an arbitrary staff string; WebSocket admission has no staff gate. The probe succeeded with `DEMO_MODE=false`, so this also bypasses the existing demo-mode boundary. Apply server-side staff authorization to list, acknowledgement and WebSocket admission; derive the actor from that identity. This is a regression in protection relative to existing doctor routes, not merely missing future production login.

**Priority 1 — safety-screening correctness and delivery**

3. **New alerts are never broadcast, despite the patient being told staff were notified.** [adaptive.py](../backend/app/services/adaptive.py:230) invokes persistence; [red_flags.py](../backend/app/services/red_flags.py:219) creates an audit record but does not call the notifier. Repository search finds an actual broadcast only on acknowledgement. An API probe created a fever alert and observed zero notifier calls. Meanwhile [patient copy](../frontend/src/i18n/triage.ts:53) always says “Medical staff have been notified.” Emit committed creation/update/resolution events, resynchronize clients after reconnect, and use wording that reflects actual delivery/acknowledgement evidence.

4. **Safety rules mishandle negation and context.** [red_flags.py](../backend/app/services/red_flags.py:161) uses substring matching. “no blood in my sputum,” Bengali and Hindi equivalents, and even “tired” all trigger the coughing-blood rule (`red` is a substring of `tired`). The concept collector also flattens all eligible source fields, so a family-history DYSPNEA concept triggers the current-patient chest-pain rule. Preserve source context and explicitly represent negation; review the clinical rule content and required structured inputs. A simple word-boundary change alone does not solve multilingual negation.

5. **Some alert explanations assert information the conditions never test.** [The catalog](../ai/safety_rules/red_flags_v1.json:127) describes sudden-onset thunderclap headache but checks only severity; the fever-duration wording has no duration condition; the abdominal vomiting rule checks neither severity nor persistence. Other concept-based rules depend entirely on normalization: an explicitly reported breathlessness phrase produces no such alert when normalization is disabled/unavailable. Align explanations to actual evidence and collect deterministic safety-critical inputs without making provider success the only path to detection. The present content is not evidenced as clinician-approved.

6. **Acknowledged alerts remain active after the trigger is removed.** [Reconciliation](../backend/app/services/red_flags.py:281) resolves only `status == 'new'`. The probe acknowledged an alert, removed all triggering facts and found it still acknowledged/active. Separate acknowledgement history from current trigger state; record resolution and reactivation events. The dashboard also increments the acknowledgement count both after its own POST and when receiving the broadcast, causing double counting for the acting client ([triage UI](../frontend/src/routes/triage/index.tsx:87)). Derive counters from unique records or refresh authoritative counts.

**Priority 1/2 — document pipeline correctness**

7. **Current OCR output is canned content, with invented confidence.** [MockOcrProvider](../backend/app/services/ocr_provider.py:53) ignores image bytes and selects a preset prescription/lab report from the filename, assigning 0.92/0.95 confidence. An invalid byte string labeled PNG produced four lab observations at 95% confidence. This is acceptable only as clearly separated synthetic fixture behavior; it must not be presented as extraction from an arbitrary uploaded document. Real OCR, decoding/content validation, faithful evidence and calibrated-or-null confidence remain missing. Disabled OCR currently returns empty text that ingestion still marks completed.

8. **Lab rows are invisible in the doctor view.** The parser stores `structured_json.observations` ([parser](../backend/app/services/document_parser.py:141)), while [DocumentViewer](../frontend/src/components/doctor/DocumentViewer.tsx:164) reads `lab_observations`. The browser probe confirmed four stored rows and no visible table. Use one typed schema from storage through API and UI and test the actual integration. The parser also invents `flag = 'Normal'` when the document omits a flag ([line 137](../backend/app/services/document_parser.py:137)); keep missing flags null/unknown.

9. **Input and storage failure handling need hardening.** Upload `document_type` is a plain unrestricted string; an unsupported value is committed, then response validation returns HTTP 500. Subsequent reads encounter the invalid stored value. The generic [exception logger](../backend/app/main.py:92) logs the submitted bad value as part of the response-validation exception. Validate before committing and log safe failure categories. File validation checks MIME labels/length, not actual image/PDF contents. Files are written before DB success without compensating cleanup. The [path guard](../backend/app/services/storage.py:71) uses string prefix matching, allowing a sibling such as `uploads_other` through a root named `uploads`; use resolved path containment. Current object keys are server-generated, so that last probe demonstrates a defective guard, not a proven unauthenticated arbitrary-file-read exploit.

**Priority 2 — voice/BHASHINI verification**

10. **The “never on disk” audio claim is false for current multipart handling.** A 2 MiB synthetic upload was already spooled to a temporary disk file when the speech service began—even though voice consent was absent and the service returned 403. The installed Starlette multipart parser spools files above 1 MiB before the service-level check. This establishes temporary disk handling, not permanent audio retention. Implement the required upload/consent boundary or accurately document secure temporary spooling and cleanup.

11. **Voice provenance is not enforced at answer submission.** The adaptive answer schema accepts `source='voice'`, but submission does not require voice consent or establish a confirmed ASR candidate. The probe saved a voice-labeled answer without voice consent. The frontend confirmation UI alone does not enforce this backend invariant. Transcription also receives arbitrary question IDs without checking the current eligible question.

12. **BHASHINI is an unverified live adapter.** No local credentials are configured. The browser records its native format/rate, while [the adapter](../backend/app/services/bhashini_speech.py:294) declares 16 kHz without decoding/resampling or checking the actual rate. Actual accepted formats/rates and multilingual results need live evaluation. The advertised one-hour cache is per provider instance, but [the factory](../backend/app/services/speech_provider.py:231) creates a new instance for each call. Discovery plus compute has transport timeouts, but no overall service deadline comparable to normalization. Direct-inference-only configuration is also blocked by startup's unconditional requirement for discovery API key and user ID. These are separate implementation/acceptance issues; no live BHASHINI success was inferred from mocked tests.

**Evidence and documentation gaps**

- `docs/implementation-status.md` names Phase 5 and 250 tests in one section; the later summary names 270; actual current tests total 280 and the API reports Phase 6.
- The Phase 5 report calls the system production-ready, while current staff endpoints bypass authorization and the rule content is unvalidated. The broad summary's “clinically curated,” “clinical-grade” and PII “scrubbed” wording is unsupported. NVIDIA omits identifying metadata; it does not redact identifiers embedded in free text. Voice audio is likewise not automatically de-identified.
- Existing NVIDIA artifacts show three validated live successes, many timeouts and no conclusive response-format capability result. The JSON-schema/object probes timed out; that does not establish that those modes are unsupported. Prompt JSON plus strict application validation is implemented; reliable EN/BN/HI, negation and uncertainty live acceptance remains open.
- `alembic check` reports `alerts.created_at` nullability drift. Current migration verifiers checking table presence must not substitute for model/schema comparison.
- Ruff fails on one Phase 6 migration import. Prettier fails on 12 files, including triage, speech and document UI files. The TypeScript build and ESLint pass.
- There is no Git repository at this workspace or its parents. With multiple models editing the same folder, establish version control and phase-specific checkpoints before further work.

**Recommended next work, in order**

1. Enforce staff access, server-owned attribution and confirmed-record rules on new routes.
2. Correct alert interpretation, lifecycle and delivery; add real API-to-open-dashboard tests and clinician review of rule content. Remove unsupported claims of staff notification and clinical readiness.
3. Make document fixtures explicit, repair the API/UI schema mismatch and false “Normal” flags, validate uploads before persistence and implement real OCR with source evidence.
4. Close voice consent/provenance and temporary-audio handling gaps; configure and evaluate BHASHINI with synthetic audio, verified formats and bounded total latency. Resolve NVIDIA reliability before describing it as live-complete.
5. Fix schema drift, lint/format gates and stale browser selectors; rerun acceptance and actual restart/resume with the new document/alert records. Reconcile status/memory/roadmap documents to that evidence.
6. Only then advance to timeline/discrepancies and subsequent roadmap features.

Review artifacts are in ignored `.runtime`: `review-tests/` (17 defect probes), `review-document-ui.json`, `screenshots/review-document-labs.png`, Playwright traces, and `current-review-manifest.json` (142 source/config/script hashes). The live NVIDIA numbers above are retained artifacts from earlier in the session, not new hosted calls made during this audit. No BHASHINI live call or real OCR execution was performed. The app was started in explicit mock normalization mode for offline browser review; local environment credentials were not changed.
