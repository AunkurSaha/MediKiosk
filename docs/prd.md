# Product Requirements Document — MediKiosk

## 1. Product name

**MediKiosk — AI-Powered Pre-Consultation Clinical Intake**

## 2. Problem

In high-volume outpatient settings, doctors spend a significant part of a short consultation collecting history and searching through prior records.

MediKiosk moves much of that preparation **before** the consultation by collecting patient history, digitizing prior documents, structuring the information, checking explicit safety rules, and producing a physician-reviewable draft.

## 3. Product objective

Enable the doctor to begin consultation with a concise, traceable, editable representation of:
- why the patient came;
- history of present illness;
- relevant past history;
- medications/allergies;
- relevant review-of-systems answers;
- prior medical documents and extracted facts;
- chronological timeline;
- red-flag alerts;
- uncertainty/verification indicators.

## 4. Users

### Patient
Needs:
- simple low-literacy-friendly interaction;
- language choice;
- touch fallback if speech fails;
- clear consent;
- transparent confirmation of captured answers.

### Triage staff
Needs:
- immediate view of red-flag alerts;
- explanation of why an alert fired;
- patient token/kiosk/session context;
- acknowledgement workflow.

### Doctor
Needs:
- structured current history;
- previous medical timeline;
- original document access;
- extraction confidence;
- discrepancy warnings;
- ability to edit;
- ability to confirm;
- final FHIR-ready record.

### Administrator — later
Needs:
- user/role management;
- configuration;
- audit review.

Not required for the first vertical slice.

## 5. Core product journey

```text
Patient arrives
→ chooses language
→ identifies/registers
→ grants consent
→ answers voice/touch questions
→ system adapts question path
→ safety rules evaluate each new answer
→ patient uploads/scans previous records
→ OCR/extraction creates structured facts
→ timeline is built
→ patient statements + documents are compared
→ draft clinical summary is generated
→ doctor reviews, edits, verifies
→ final structured record is exportable to FHIR
```

## 6. Prototype scope

The SIH prototype should strongly demonstrate:

1. English/Bengali/Hindi-ready UI.
2. Voice architecture with touch fallback.
3. Adaptive interview engine.
4. Initial complaint families:
   - chest pain;
   - abdominal pain;
   - fever;
   - headache;
   - cough/breathlessness.
5. Continuous deterministic red-flag screening.
6. Document upload.
7. Printed OCR first; handwriting as confidence-aware fallback.
8. Medication/lab extraction.
9. Timeline.
10. Discrepancy detection.
11. Draft summary.
12. Doctor review/edit/confirm.
13. FHIR export.
14. ABDM sandbox-compatible architecture, with live integration later.

## 7. Explicit non-goals for MVP

Do not make the MVP depend on:
- real Aadhaar authentication;
- production ABHA onboarding;
- production ABDM exchange;
- full hospital HIS integration;
- every Indian language;
- every clinical complaint;
- reliable free-form handwritten-prescription understanding;
- autonomous diagnosis;
- autonomous treatment recommendation;
- medical-device-grade regulatory claims;
- national-scale deployment infrastructure.

## 8. Functional requirements

### FR-01 Language selection
The patient can select a supported UI language before clinical intake.

Initial prototype: English, Bengali, Hindi.

### FR-02 Identification
The system supports a demo patient identification flow.

Must support:
- patient name;
- hospital token;
- optional demo ABHA identifier.

### FR-03 Consent
Before medical questions, the system records granular consent for:
- voice processing;
- document processing;
- sharing with doctor.

Consent must have timestamp and session association.

### FR-04 Session
Each intake is associated with a unique session ID.

### FR-05 Interview
The system stores each answer with:
- question ID;
- normalized field;
- answer value;
- original/raw answer when applicable;
- source;
- language;
- timestamp.

### FR-06 Adaptive questions
Question selection is controlled by structured complaint flows and rules.

LLMs may interpret patient language but do not decide the entire medical interview.

### FR-07 Voice
Voice input is converted to text through a replaceable speech adapter.

Low-confidence speech should support confirmation or touch fallback.

### FR-08 Red flags
Safety rules evaluate structured facts continuously.

Alert content must explain the trigger, not assert a diagnosis.

### FR-09 Documents
The patient can upload/scans prior documents.

The system retains the original document.

### FR-10 OCR/extraction
Extracted facts must include confidence and provenance.

Low-confidence extractions are never silently marked verified.

### FR-11 Timeline
Structured facts from documents are organized chronologically when a date is available.

### FR-12 Data fusion/discrepancies
The system compares relevant patient-reported data with prior-document data and can create a verification-needed discrepancy.

### FR-13 Draft summary
A draft physician-oriented history is produced from structured data.

Summary generation must not invent unknown information.

### FR-14 Doctor review
Doctor can:
- view source information;
- edit summary;
- verify fields where applicable;
- confirm final history.

### FR-15 Audit
Clinically meaningful create/edit/confirm/view actions should be auditable.

### FR-16 FHIR export
Confirmed data can later map to FHIR resources such as:
- Patient;
- Observation;
- AllergyIntolerance;
- Condition where appropriate and clinician-confirmed;
- MedicationStatement/related medication resource as appropriate;
- Composition/Bundle.

Implementation details are deferred to the FHIR phase.

## 9. Non-functional requirements

### Safety
Human review is mandatory before AI-derived draft information becomes a confirmed clinical record.

### Explainability
Safety alerts and uncertainty must be traceable.

### Accessibility
Prefer:
- large targets;
- high contrast;
- simple wording;
- one primary action per patient screen;
- voice + touch alternatives.

### Performance
For deterministic CRUD operations, target responsive local-demo interactions. External AI latency must not block basic navigation without feedback.

### Reliability
Failure of LLM/OCR/speech providers must degrade gracefully.

### Privacy
No patient data should remain visible on the kiosk after session completion/logout.

### Maintainability
Use provider interfaces, typed schemas, versioned rule/config files, migrations, and tests.

## 10. Success criteria for SIH demo

A strong demo should show a Bengali-speaking patient flow where:

1. patient selects Bengali;
2. grants consent;
3. reports chest pain;
4. structured chest-pain flow continues;
5. exertional worsening + breathlessness causes an explainable urgent alert;
6. old prescription is uploaded;
7. medicine extraction is shown with confidence;
8. lab result is extracted;
9. timeline is built;
10. doctor opens the patient token;
11. doctor sees current history + previous records + alert;
12. doctor edits and confirms a draft summary;
13. system can show/export a FHIR-compatible representation.

## 11. Product principle

**The system prepares. The clinician decides.**
