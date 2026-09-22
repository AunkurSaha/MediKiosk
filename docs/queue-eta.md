# Visit queue reservation and ETA (prototype)

The existing `doctor_queue_entries` record is the operational source of truth. A non-emergency visit receives exactly one entry only when a completed intake is successfully submitted. Doctor or facility selection alone never reserves a place. The unique `session_id` constraint makes retries idempotent, and the submitted assignment is frozen.

Each queue is scoped to `facility + doctor + UTC service date`. Its patient-facing token is server generated as `MK-{first four specialty characters}-{three digit daily sequence}`. The token contains no patient information and is a display identifier, not an authorization credential or an external hospital appointment.

The canonical state machine is `WAITING → CALLED → IN_CONSULTATION → COMPLETED`; `WAITING` or `CALLED` may instead become `CANCELLED`. Other transitions return `INVALID_QUEUE_TRANSITION`. Only the assigned doctor with an active membership at the visit facility can transition an entry. Patients may read only the queue associated with their owned session and cannot mutate it. Triage staff receive no doctor queue-management privilege.

For a waiting patient, position is derived on every request from `WAITING` and `CALLED` entries in the same queue, ordered by `joined_at` and then queue-entry ID. Completed and cancelled entries do not count. The versioned policy in `ai/queue/eta_policy_v1.json` estimates `patients ahead × average consultation minutes`; version 1.0 uses 12 minutes. It is explicitly an estimate and no exact meeting time is promised.

Emergency visits bypass the normal doctor queue and receive no token. Queue metadata is operational and remains separate from clinical evidence, summaries, FHIR, and ABDM.

Synthetic verification uses only `scripts/start-e2e.ps1`, `scripts/verify-phase5-e2e.py`, the Phase 5 Playwright suite, and the ignored `.runtime/e2e.sqlite`. It must never contain real patient data or modify remote Supabase.
