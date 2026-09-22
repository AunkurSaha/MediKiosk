# Continuity of care: Phase 9A foundation

Phase 9A adds a read-only continuity analysis for a current MediKiosk session. It reuses the append-only Clinical Evidence Graph; it neither copies prior evidence into the current encounter nor promotes it to current truth.

Eligible prior encounters belong to the same canonical patient ID, exclude the current session, and have a completed review lifecycle state (`ready_for_review`, `under_review`, or `confirmed`). They are ordered by the persisted completion time, falling back to creation time only where completion time is unavailable, most recent first. Incomplete and abandoned sessions are excluded.

`GET /api/sessions/{session_id}/continuity` returns prior-visit metadata, source-attributed historical evidence, a deterministic change set, and items that can later be used for explicit reconfirmation. Patient access is limited to the owned session; doctor access reuses selected-doctor and active-facility authorization; triage is denied. The endpoint is read-only and does not create evidence, answers, audits, or packet data.

Authority is explicit: current patient-confirmed evidence, current clinician-verified evidence, current document evidence, later explicit reconfirmation, historical evidence, machine suggestion, then missing. Historical evidence is never automatically current. `NEW` means current evidence has no prior equivalent; `UNCHANGED` requires equal current and historical evidence; `CHANGED` means equivalent evidence differs; `RESOLVED` requires an explicit current negative medication-style report; `CONFLICTED` is an explicit allergy-style denial; and `HISTORICAL_ONLY` means a prior fact has no current confirmation. `UNKNOWN_CURRENT_STATUS` is reserved for a later explicit “not sure” reconfirmation flow.

Acute historical symptoms remain historical and are not promoted into the current encounter. Historical labs and document provenance remain dated, source-linked evidence; the comparison service makes no trend, diagnostic, or treatment inference. `longitudinal_timeline` is a deterministic ordered view of prior and current evidence references, not a persisted copy or a replacement for the encounter timeline.

## Phase 9B reconfirmation

Phase 9B adds one deterministic, patient-facing reconfirmation turn only when the
existing adaptive flow reaches `medications.details` or `allergies.details`. It is
therefore after the configured chief complaint, safety, and HPI questions; prior
acute symptoms and historical red flags are never inserted into a new encounter.

The synthetic question has a stable `continuity.<historical-evidence-id>` identity
and uses the existing answer, translation, touch, voice, audit, and idempotency
paths. It is labelled “From your previous visit” in the existing interview UI.
Historical evidence stays immutable. Every resulting current evidence row records
the historical evidence ID and source session ID in provenance metadata.

Medication `yes` projects the prior value into ordinary current patient-confirmed
flow answers and suppresses the now-redundant configured detail question. `no`
records an explicit current negative; `changed` leaves the configured detail turn
available for the new value; and `not_sure` remains unresolved. Allergy `yes` and
`no` follow the same current-evidence rule, with an allergy `no` represented as an
explicit current denial. Historical evidence alone never satisfies coverage.
