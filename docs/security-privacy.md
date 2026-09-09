# Security & Privacy — MediKiosk

This is an SIH prototype security baseline, not a claim of production compliance certification.

## 1. Data minimization

Collect only what the prototype needs.

Do not collect Aadhaar details or real ABHA credentials just to make the demo look realistic.

Prefer synthetic patient data in development/demo.

## 2. Consent

Consent precedes clinical processing.

Store consent:
- per session;
- with individual processing purposes;
- with timestamp;
- with version if consent text changes later.

## 3. Authentication and authorization

When staff auth is introduced:
- server-side role enforcement;
- doctor and triage permissions separated where relevant;
- password hashes only;
- never trust role claims from frontend without backend verification.

JWT/session strategy can be decided during auth implementation.

## 4. Secrets

Secrets belong in environment variables or deployment secret stores.

Never commit:
- DB passwords;
- JWT signing secrets;
- LLM keys;
- BHASHINI credentials;
- object-storage secret keys;
- ABDM credentials.

Provide names only in `.env.example`.

## 5. Logging

Application logs should default to:
- request IDs;
- route;
- status;
- timing;
- technical error details.

Avoid logging:
- full patient answers;
- full OCR text;
- document contents;
- credentials;
- tokens.

## 6. Documents

- Validate media type and size.
- Generate server-side object keys.
- Do not trust original filename as path.
- Do not expose bucket credentials.
- Prefer authorized download endpoints/presigned access when implemented.
- Preserve original source for clinician verification.

## 7. Kiosk privacy

At session end:
- clear local patient state;
- clear temporary audio references;
- revoke object URLs;
- navigate to a clean welcome screen.

Avoid storing clinical data in long-lived browser storage unless explicitly needed and secured.

## 8. Audio Privacy & Ephemeral Processing (Phase 4A)

- **Zero Raw Audio Storage**: Raw audio is NEVER permanently stored. There is no `audio` table in PostgreSQL, no raw audio sent to object storage (MinIO/S3), and no permanent filesystem retention.
- **Ephemeral Backend Processing**: Temporary files created on the backend for provider communication use server-generated UUID filenames (`uuid.uuid4()`) in the system temp directory (never trusting client filenames). Files are context-managed and deleted immediately in a guaranteed `finally` block (`os.unlink()`) on success, provider failure, validation rejection, or timeout.
- **Ephemeral Browser State**: Audio chunks recorded via `MediaRecorder` reside in volatile browser RAM only during the recording session. Memory references and object URLs are revoked/garbage-collected immediately upon submission or cancellation. Blobs are never persisted to `localStorage`, `sessionStorage`, or `IndexedDB`.
- **Mandatory Voice Consent**: Voice processing is strictly gated behind explicit opt-in consent (`voice_processing: true`). The backend verifies this before processing any audio, returning HTTP 403 `VOICE_CONSENT_REQUIRED` if consent is not granted.
- **Upload Resource & Size Limits**:
  - Maximum upload size: 5MB (`5 * 1024 * 1024` bytes). Oversized payloads receive HTTP 413 `FILE_TOO_LARGE`.
  - Empty uploads (0 bytes) are rejected with HTTP 422 `EMPTY_AUDIO`.
  - Allowed MIME types: `audio/webm`, `audio/ogg`, `audio/wav`, `audio/mp4`, `audio/mpeg`. Unsupported types receive HTTP 415 `UNSUPPORTED_MEDIA_TYPE`.
- **Candidate Transcription Isolation**: Raw ASR transcript is treated strictly as an unconfirmed candidate. It is never automatically committed to clinical state or clinical history. Only the patient's explicitly confirmed (or edited) text is persisted.
- **TTS Question Minimization**: Text-to-speech synthesizes strictly the static, localized question text from the pinned complaint flow snapshot. Patient answers, clinical history, PII, and doctor summaries are never sent to TTS.


## 9. AI providers

Do not send patient data to an external AI provider until:
- provider is configured intentionally;
- data sent is minimized;
- project owner understands provider handling;
- a mock/local mode exists for normal development.

The code should make the provider boundary visible.

### Phase 3B NVIDIA NIM Provider Privacy & Secret Controls:
- **Input Minimization**: Only `text`, `language`, and `canonical_field` are transmitted. Context parameters (`flow_id`, `question_id`, `patient_name`, `session_id`, `demo_abha_id`, `hospital_token`) are strictly excluded before transmission.
- **Key Safety**: `NVIDIA_API_KEY` is loaded from backend environment configuration into a Pydantic `SecretStr(exclude=True, repr=False)`. It is never returned in API responses, serialized into configuration dumps, or printed to stdout/logs.
- **No Secret/PHI Logging**: Technical logs record latency, HTTP status, and token counts only. Request bodies, authorization headers, and raw model responses containing patient text are never logged.
- **Value-Based Audit**: Regular automated audits verify that the configured API key does not appear anywhere in repository code, tests, documentation, or log files (`audit-phase3b-secrets.py`).


## 10. Database

Use separate DB user/password for the app.

Production deployment should use encrypted transport and restricted network access.

## 11. Web/API

- CORS allowlist in non-local deployments.
- Request validation via Pydantic.
- upload limits.
- CSRF strategy if cookie-based auth is chosen.
- rate limiting can be added for exposed deployments.
- no stack traces in user responses.

## 12. Audit

Audit meaningful actions:
- viewing clinical detail if required;
- editing reviewed summary;
- confirming summary;
- acknowledging safety alert;
- exporting/sharing data.

Audit logs should record event metadata, not duplicate full PHI.

## 13. Demo safety

Use fictional patient scenarios.

Clearly label integration screens as:
- demo;
- mock;
- sandbox;
when they are not connected to real systems.

## 14. Compliance posture

The project is designed with consent, access control, provenance, and auditability in mind.

Do not make legal/regulatory compliance claims in code/UI unless separately verified for the actual deployment.
