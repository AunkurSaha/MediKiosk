# MediKiosk API contract — through Phase 5

Base: `/api`. Local OpenAPI: http://127.0.0.1:8010/docs. All request schemas reject unknown fields. Identity/review text is trimmed; adaptive raw wording is retained exactly. Timestamps have explicit UTC offsets.

## Errors and health

Errors have `{ "error": { "code": "...", "message": "...", "details": null } }`. Validation details contain field/type names without echoing patient values. Status codes: 404 missing resource, 422 invalid input, 409 workflow/revision conflict, 401 missing demo doctor identity, 403 missing consent/forbidden role, 503 database unavailable.

`GET /health` checks the database and returns `{"status":"ok"}`. `GET /config` returns demo mode, `phase: "5"`, `languages: ["en","bn","hi"]`, `speech_provider: "mock"`, and `normalization_provider`, without secrets.

## Session identity and consent

`POST /sessions` creates patient and session atomically, returning 201:

```json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "patient": {"name":"Synthetic Patient","demo_abha_id":null},
  "hospital_token":"DEMO-104",
  "language":"en"
}
```

Retain the client UUID before sending. Repeating the same ID/details returns the same session; changed identity data returns `ID_CONFLICT`. There is no patient CRUD/deletion endpoint.

`GET /sessions/{id}` returns `{session, patient, consent, answers, summary, history}`. Answers are latest **active** answers in configuration order; all historical corrections remain stored. History is a typed `ClinicalHistory` or null before any selected flow/legacy answers. The browser stores only the session UUID; clinical data is reloaded from the server. UUID possession is a local-demo convenience, not production authorization.

`PUT /sessions/{id}/consent` upserts one consent record and writes audit metadata:

```json
{"voice_processing":false,"document_processing":false,"share_with_doctor":true}
```

Voice processing consent can now be set to `true` or `false`. If `voice_processing` is `false`, microphone input is disabled in UI and any transcription attempt returns HTTP 403 `VOICE_CONSENT_REQUIRED`. Document processing flag must remain false. Clinical answers, adaptive state/selection/navigation, completion and doctor detail require sharing consent. Consent cannot change after completion.

## Adaptive interview state and selection

`GET /sessions/{id}/interview` returns `InterviewState`. Before selection, `selection_required` is true and `flows` contains five standard choices and the separately namespaced AYUSH demonstration. All display labels have en/bn/hi translations.

`PUT /sessions/{id}/interview/flow` with `{"flow_id":"chest_pain"}` pins the current flow version and full validated snapshot, then returns state. Repeating the same selection is safe. A different flow returns `FLOW_LOCKED`; use a new intake to change complaints. `legacy.intake` cannot be explicitly selected.

State includes:

| Field | Meaning |
|---|---|
| flow_id / flow_version / namespace | Pinned configuration identity |
| revision | Optimistic revision for answer/cursor mutations |
| section | Current section label in three languages |
| question | Renderable stable ID, canonical field, type, text, options, constraints and policy; null at end |
| current_answer | Previously saved fact for the current question, if any |
| previous_question_id | Server-provided back target |
| active_answers | Latest applicable saved facts, in configuration order |
| inactive_question_ids | Historical answered questions whose branches are inactive |
| missing_required | Applicable required questions without an explicit response |
| progress | Addressed/applicable counts and current position; total can change after branching |
| is_complete | All applicable questions have an explicit response |
| history | Typed active history with provenance |
| red_flag_alert | Highest active priority safety screening alert (`AlertSummary` or null) |

The frontend must not evaluate returned branch metadata or calculate the next question. Ordered applicability, conditions and completion are backend responsibilities.

## Submit a typed answer

`POST /sessions/{id}/interview/answers` returns recalculated state:

```json
{
  "request_id":"22222222-2222-4222-8222-222222222222",
  "expected_revision":0,
  "question_id":"chief_complaint.description",
  "status":"answered",
  "value":"My original words",
  "raw_value":"My original words",
  "source":"typed",
  "language":"en"
}
```

Submission is allowed only for the current active question, in the session language. Source is typed, touch, or voice; only the server sets patient_reported verification. The reported answer is never overwritten by normalization. Optional machine enrichment is separate, as described in the Phase 3A contract below.

| Question type | Answered value |
|---|---|
| short_text | Nonblank string within configured maximum; raw/value text must agree exactly |
| boolean | JSON true/false, never string or number coercion |
| single_choice | One configured option code |
| multiple_choice | Nonempty unique array of configured codes; exclusive options cannot be combined |
| number | Finite number within configured bounds |
| severity | Integer 0–10 |
| duration | `{ "amount": 2, "unit": "days" }`; units minutes/hours/days/weeks/months/years |

Statuses are answered, unknown, not_reported or skipped. The last three require `value: null` and explicit raw display wording. Unknown/not_reported are accepted only when allowed by the question; skipped only on optional questions. These are distinct from “No”, zero, or an unanswered question. Required questions with allowed explicit unknown/not-reported are addressed; they are not interpreted as negative findings.

Retain exactly the same request UUID and payload for a retry. The database stores a payload hash keyed by session/request ID; duplicate and delayed retries return the current state without appending rows, moving the cursor backwards or undoing corrections. Reusing an ID with different data returns ID_CONFLICT. A new request with a stale expected_revision returns INTERVIEW_CONFLICT. Reload state before continuing; never silently overwrite a later edit.

Corrections append new interview_answer rows. Saving an identical current value/raw/status/source does not append another answer. The mutation, receipt, cursor/revision and audit event commit together under a PostgreSQL session-row lock.

## Back/edit and branch recalculation

`PUT /sessions/{id}/interview/cursor`:

```json
{"question_id":"past_medical_history.diabetes","expected_revision":12}
```

Only active answered questions or the first pending question may be opened. The server returns the saved value and a new revision. Stale navigation returns a conflict and requires reload. No answers are deleted by navigation.

Conditions inspect active answered parents only. Editing diabetes Yes → No hides follow-ups from current history and completion requirements while retaining their rows. No → Yes restores the latest historical follow-up answers, with original IDs, raw wording and provenance. Forward traversal displays restored answers for review. Unknown parents do not activate yes branches.

## Phase 1 compatibility

`POST /sessions/{id}/answers` remains for legacy sessions without a persisted interview_run. It accepts the original five text fields chief_complaint, onset_duration, medications, allergies and past_history, with question_id=field, matching raw/value text, typed/touch source and matching language. Existing Phase 1 tests and records remain supported. Once a run exists, this write endpoint returns ADAPTIVE_API_REQUIRED.

Retained legacy answers can resume through the adaptive state API using the authoritative `legacy/intake.json`; the first adaptive mutation pins that compatibility flow. New empty kiosk intakes always receive complaint selection.

`GET /sessions/{id}/answers` returns latest active answers, preserving value type and explicit status. Older JSON-string rows appear as answered text.

## Completion and structured history

`POST /sessions/{id}/complete` requires consent and every applicable question addressed. Optional questions may explicitly be skipped. Legacy clients without a run retain the five-required-text-fields rule.

Completion atomically marks ready_for_review, stores completed_at, creates a deterministic draft and typed structured snapshot, and writes audit metadata. Repeating completion does not create another summary. Completed/confirmed intake answers, flow selection and navigation are locked.

`ClinicalHistory` schema 1 contains flow identity/version/namespace, selected complaint/source and typed sections. Each section has a canonical enum ID and ordered facts; facts carry answer ID, question ID, canonical field, localized label, typed value, explicit status, raw wording, source, language, recorded timestamp and patient_reported verification. Empty sections remain explicit. The AYUSH section is isolated. Generated prose is not the canonical representation.

The completion snapshot uses the existing `generated_structured_json` summary field. Current history is also available as the typed `history` property in patient/doctor detail and interview state.

## Doctor review and confirmation

Doctor routes require DEMO_MODE=true, a seeded active doctor and X-Demo-Doctor: true. Demo access is unavailable in production; real staff authentication and patient capability tokens remain future hardening.

- `GET /doctor/sessions` returns `{items:[...]}` for consented completed intakes, including patient names/tokens/status.
- `GET /doctor/sessions/{id}` returns detail with active grouped history, provenance and summary; viewing is audited.
- `PUT /doctor/sessions/{id}/summary` accepts `{"reviewed_text":"Reviewed history","expected_version":1}`. Text is 1–64,000 characters. It preserves both generated fields, increments version, appends a review revision and records server-owned reviewer/time.
- `POST /doctor/sessions/{id}/summary/confirm` accepts `{"expected_version":2}`. It requires a saved review and matching version, records doctor/time and makes the record immutable. An identical confirmation retry preserves its timestamp.

Concurrent doctor mutations are serialized by the same session-row lock. Clients cannot set generated facts, verification identity, timestamps or status. No voice, document, alert, timeline, provider, FHIR or ABDM endpoints are exposed.

## Phase 3A additive normalization contract

No additional public endpoint or changed answer-submission payload. `Fact.normalization` is now included in interview state/history and patient/doctor structured history:

- null: this field/type is not eligible (for example numeric, choice or AYUSH).
- normalized: validated machine facts with source/provenance.
- unrecognized: eligible wording was not in the fixture vocabulary; facts empty, reason no_match.
- unknown: explicit missing-information state/fixture; facts empty, reason explicit_unknown.
- unavailable: timeout, provider_unavailable, unsupported_language, invalid_result, disabled, or not_processed; facts empty.

Each normalization exposes id, source_answer_id, source_question_id, canonical_field, original_text/language, provider/version, schema/policy versions, created_at and status/reason. Each derived fact exposes normalized_concept/display/value, exact evidence, confidence (nullable), certainty and machine_normalized/needs_verification status. Neither means clinician verification. Current source wording/value/verification fields remain unchanged.

Strict provider output only accepts the supplied field/language, schema 1.0, allowed symptom/qualitative concepts, valid confidence/certainty and source evidence. Diagnosis/treatment/extra fields fail closed. Trusted display/value and all provenance are service-owned. No provider credentials or internal exceptions are returned.

Results are immutable per source answer and reused on retry/branch reactivation. Source edits generate a new result; only current active-source results appear in history. Historical and confirmed records are not backfilled/reprocessed. Summary confirmation never promotes machine facts. Original generated text/JSON remain preserved. `/api/config` now returns `phase: "3B"` and `normalization_provider`.

## Phase 3B additive normalization contract & Schema 1.1

No additional public endpoint or changed answer-submission payload. The contract is backward-compatible with Phase 3A:

- `/api/config` returns:
  ```json
  {
    "demo_mode": true,
    "phase": "3B",
    "languages": ["en", "bn", "hi"],
    "normalization_provider": "nvidia"
  }
  ```
- Configuration via environment:
  - `CLINICAL_NORMALIZATION_PROVIDER`: `mock` | `nvidia` | `disabled`
  - `NVIDIA_API_KEY`: Secret string, never exposed via API
  - `NVIDIA_BASE_URL`: Defaults to `https://integrate.api.nvidia.com/v1`
  - `CLINICAL_NORMALIZATION_MODEL`: Defaults to `google/gemma-4-31b-it`
  - `CLINICAL_NORMALIZATION_TIMEOUT_SECONDS`: `8` (default) to `15` seconds
  - `CLINICAL_NORMALIZATION_MAX_TOKENS`: `768` (default)

- **Schema 1.1 Facts**:
  When `schema_version == "1.1"` (live NVIDIA provider output):
  - `polarity`: required `"present"` | `"absent"`
  - `certainty`: `"certain"` | `"uncertain"`
  - `confidence`: `null` (no hallucinated probability scores)
  - `evidence`: exact substring from the patient's untrusted input
  - Additional provenance in `Fact.normalization`:
    - `model`: `"google/gemma-4-31b-it"`
    - `prompt_version`: `"nvidia-1.0"`
    - `latency_ms`: measured round-trip time
    - `token_usage`: `{"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}` when provided

- **Failure Semantics**:
  If NVIDIA is unavailable, times out, or fails validation:
  - Patient answer commits successfully; interview continues uninterrupted.
  - Normalization status becomes `"unavailable"` with durable reason:
    `"timeout"` | `"network_error"` | `"authentication_failed"` | `"rate_limited"` | `"server_error"` | `"invalid_result"`.
  - No silent fallback to mock provider occurs.

## Phase 4A Speech and Text-to-Speech (TTS) contract

### Speech-to-Text (ASR) Candidate Transcription

`POST /api/sessions/{session_id}/interview/speech/transcribe`

Accepts multipart form upload:
- `audio`: binary audio file (supported types: `audio/webm`, `audio/ogg`, `audio/wav`, `audio/mp4`, `audio/mpeg`). Capped at 5MB (`5 * 1024 * 1024` bytes). Empty uploads rejected.
- `language`: optional language string (`en`, `bn`, `hi`). If provided, must match session language.

Preconditions enforced:
1. Session exists and is editable (`ready_for_review == false`, `is_confirmed == false`).
2. Sharing consent (`share_with_doctor == true`) is granted.
3. Voice consent (`voice_processing == true`) is explicitly granted (HTTP 403 `VOICE_CONSENT_REQUIRED` if false).
4. Audio size <= 5MB (HTTP 413 `FILE_TOO_LARGE` if exceeded).
5. Audio content is non-empty (HTTP 422 `EMPTY_AUDIO` if empty).
6. Audio MIME type is supported (HTTP 415 `UNSUPPORTED_MEDIA_TYPE` if unsupported).

Processing & Privacy:
- Raw audio is streamed to an ephemeral server-side temporary file with a random UUID name.
- Temporary file is strictly unlinked in a `finally` block on success, provider error, validation error, or timeout.
- Zero raw audio is saved to PostgreSQL, object storage, or filesystem.
- Transcription output is strictly a **candidate transcript** and is NEVER persisted as an interview answer automatically.

Response:
```json
{
  "transcript": "I have chest pain",
  "language": "en",
  "confidence": null,
  "provider": "mock",
  "model": "deterministic-mock",
  "status": "success",
  "reason": null
}
```

On provider failure:
```json
{
  "transcript": null,
  "language": "en",
  "confidence": null,
  "provider": "mock",
  "model": "deterministic-mock",
  "status": "unavailable",
  "reason": "timeout"
}
```

### Text-to-Speech (TTS) Question Synthesis

`POST /api/sessions/{session_id}/interview/speech/synthesize`

Request:
```json
{
  "question_id": "chief_complaint.description"
}
```

Preconditions enforced:
1. Session exists.
2. Sharing consent (`share_with_doctor == true`) is granted.
3. `question_id` must match a question defined in the session's pinned flow snapshot (HTTP 404 `QUESTION_NOT_FOUND` if invalid).

Processing & Safety:
- Text is extracted strictly from the localized text field of the pinned complaint flow snapshot for the session's active language.
- Patient-reported answers, clinical histories, and doctor summaries are never passed to TTS.
- Returns synthesized audio bytes or mock audio representation.

Response:
```json
{
  "audio_base64": "UklGRj4AAABXQVZFZm10IBAAAA...",
  "mime_type": "audio/wav",
  "language": "en",
  "text_synthesized": "Describe your main concern in your own words.",
  "provider": "mock",
  "status": "success",
  "reason": null
}
```

## Phase 5: Staff Triage & Safety Screening Endpoints

### List Triage Alerts

`GET /api/triage/alerts`

Query parameters:
- `status`: Optional filter (`"new"`, `"acknowledged"`, `"resolved"`).
- `priority`: Optional filter (`"emergency"`, `"urgent"`).

Response (`AlertList`):
```json
{
  "items": [
    {
      "id": "alert-uuid",
      "session_id": "session-uuid",
      "rule_id": "RF-CHEST-001",
      "rule_version": "1.0.0",
      "priority": "emergency",
      "category": "cardiovascular",
      "reason": "Severe radiating chest pain (potential acute coronary syndrome).",
      "triggering_facts": [
        {
          "question_id": "hpi_severity",
          "field": "hpi.severity",
          "value": 9,
          "raw_value": "9",
          "label": "Severity"
        }
      ],
      "status": "new",
      "acknowledged_at": null,
      "acknowledged_by": null,
      "acknowledgement_note": null,
      "created_at": "2026-09-09T12:00:00Z",
      "updated_at": null,
      "hospital_token": "DEMO-104",
      "patient_name": "Synthetic Patient"
    }
  ],
  "total": 1,
  "emergency_count": 1,
  "urgent_count": 0,
  "acknowledged_count": 0
}
```

### Acknowledge Alert

`POST /api/triage/alerts/{alert_id}/acknowledge`

Request (`AlertAcknowledgeRequest`):
```json
{
  "acknowledged_by": "Nurse Ratched",
  "note": "Patient moved to resuscitation bay for immediate ECG"
}
```

Response (`AlertItem`): returns the updated alert record with `status: "acknowledged"`, `acknowledged_at` timestamp, and `acknowledged_by` staff name. Emits an `alert_acknowledged` event over the WebSocket feed.

### Session Alerts

`GET /api/sessions/{session_id}/alerts` or `GET /api/triage/sessions/{session_id}/alerts`

Returns `list[AlertItem]` for the specified session, ordered by emergency priority first, then creation timestamp.

### Live Triage WebSocket Feed

`WebSocket /api/triage/ws`

Connected staff clients receive real-time JSON frames:
- `{"type": "alert_created", "alert": {...}}`
- `{"type": "alert_acknowledged", "alert": {...}}`


