# Chief Complaint and Rapid Clinical Routing

Status: deterministic prototype; clinical and translation review are required before real-world use.

## Purpose and boundary

The rapid interview answers: **How urgent is this and what broad care path is appropriate?** It is a short safety/routing protocol and is not a diagnosis.

The later full clinical interview answers: **What detailed history should the clinician receive?** It remains the existing adaptive interview and is not replaced by this feature.

RAG/LLM output may assist with language understanding in future, but cannot select urgency. Only versioned deterministic rules may produce `EMERGENCY` or `URGENT`.

## Patient flow

After consent, the kiosk asks “What is bothering you today?” The patient may choose a card, type, or use the consent-gated voice pipeline. Typed/voice wording maps to one constrained category and must be explicitly confirmed before routing begins.

Supported categories are `CHEST_DISCOMFORT`, `FEVER`, `HEADACHE`, `BREATHING_DIFFICULTY`, `ABDOMINAL_PAIN`, `COUGH`, `SKIN_PROBLEM`, `INJURY`, `JOINT_PAIN`, and `OTHER`. English, Bengali, and Hindi labels are shown in the kiosk.

Question definitions live in `ai/rapid_routing/questions_v1.json`. The initial detailed protocols cover the complaint families already supported by deterministic flows; other categories intentionally use a minimal direct broad-specialty route.

## Evidence and persistence

Confirmed complaints create `CHIEF_COMPLAINT` evidence with the original/translated text, language, input source, mapping provider, ASR provenance where applicable, and `PATIENT_CONFIRMED` status. Each rapid answer is an ordinary `InterviewAnswer` and is projected into `ClinicalEvidence`; no hidden fact store is used.

Before asking a question, routing checks evidence with `PATIENT_CONFIRMED` or `CLINICIAN_VERIFIED` status for its target/equivalent field. `UNVERIFIED` OCR evidence never satisfies a mandatory safety question.

`RapidRoutingRun` persists complaint, confirmation, protocol version, and optimistic revision. `ClinicalRoutingResult` persists urgency, broad specialty, supporting evidence IDs, triggered rule IDs, asked/skipped questions, and completion time. `GET /sessions/{id}/rapid-routing` restores any step after refresh.

## Care states and emergency bypass

Allowed states are `EMERGENCY`, `URGENT`, `ROUTINE_OPD`, and `TELECONSULT_MAY_BE_SUITABLE`. There is deliberately no `NO_DOCTOR_REQUIRED` state.

Emergency results show “Potential emergency symptoms detected” and recommend immediate in-person assessment. They do not show or enter normal doctor selection. Non-emergency results show urgency and one broad department, then allow continuation to the existing detailed interview.

Prototype specialty outputs are limited to `GENERAL_MEDICINE`, `CARDIOLOGY`, `PULMONOLOGY`, `ORTHOPEDICS`, `DERMATOLOGY`, and `EMERGENCY` for the active category map.

## Authorization and APIs

All endpoints reuse session ownership and consent checks:

- `GET /sessions/{session_id}/rapid-routing`
- `POST /sessions/{session_id}/rapid-routing/complaint/map`
- `PUT /sessions/{session_id}/rapid-routing/complaint`
- `POST /sessions/{session_id}/rapid-routing/answers`

Voice candidates are signed, short-lived, session/question/revision/language bound, and are verified before their transcript becomes complaint metadata.

## Deferred

Facility/location routing, doctor ranking/matching, queue ETA changes, booking, full-interview refactoring, and any LLM emergency classification are outside this phase.
