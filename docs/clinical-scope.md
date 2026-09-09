# Clinical Scope & Interview Structure — MediKiosk

This document defines the prototype's clinical **information-collection scope**, not medical diagnosis or treatment logic.

Any real-world clinical rule set must be reviewed by qualified clinicians before deployment.

## 1. Standard history structure

The interview engine should ultimately be capable of building:

```text
Chief Complaint
→ History of Present Illness (HPI)
→ Past Medical History
→ Past Surgical History
→ Current Medications
→ Drug/Food Allergies
→ Family History
→ Personal History
→ Review of Systems
```

Do not force every section into one long fixed questionnaire. Use:
- small core set;
- complaint-specific branches;
- condition-specific branches;
- skip logic based on prior answers.

## 2. Initial complaint families

Prototype focus:

1. Chest pain
2. Abdominal pain
3. Fever
4. Headache
5. Cough / breathlessness

Implement these well before broadening coverage.

## 3. Pain history

For pain complaints, the interview may use a structured SOCRATES-like representation:

- site;
- onset;
- character;
- radiation;
- associated symptoms;
- timing;
- exacerbating factors;
- relieving factors;
- severity.

The UI wording should remain natural and patient-friendly.

## 4. Condition-specific branches

Example concept:

```text
Do you have diabetes?
├── No → continue
└── Yes
    ├── duration
    ├── current medicines
    ├── insulin use if relevant to configured flow
    └── relevant previous monitoring information
```

This is a branch model, not a rule to diagnose diabetes.

## 5. AYUSH mode

The original project scope includes an AYUSH-oriented pathway.

Treat AYUSH as an **explicit mode/configuration**, not something mixed silently into the standard allopathic history flow.

Target structured categories include the planned Dashavidha-style fields:

- Prakriti
- Vikriti
- Sara
- Samhanana
- Pramana
- Satmya
- Sattva
- Ahara Shakti
- Vyayama Shakti
- Vaya
- relevant Ahara-Vihara context

For the SIH prototype, one demonstrable AYUSH pathway is sufficient unless the team chooses to expand it.

Implementation guidance:
- put AYUSH question configuration under its own namespace/file;
- label the mode clearly;
- keep it separate from red-flag/emergency safety screening;
- preserve the same consent/provenance/doctor-review principles.

## 6. Red-flag scope

Red-flag evaluation runs continuously over structured answers.

Rules must be:
- deterministic;
- versioned;
- explainable;
- tested;
- treated as prototype rules until clinically reviewed.

The output is an alert recommending priority assessment, never a diagnosis.

## 7. Missing/uncertain information

Use explicit values/states such as:
- not asked;
- not reported;
- unknown;
- patient unsure;
- low confidence;
- needs verification.

Do not convert missing data to “No”.

## 8. Patient vs document conflict

Example:

```text
Patient reports: no regular medicines
Previous prescription: Amlodipine 5 mg OD
```

Expected behavior:
- create a discrepancy;
- show both sources;
- request verification.

Do not silently choose one.

## 9. Language normalization

Patient-facing interaction may remain in Bengali/Hindi/English while internal concepts use canonical identifiers/English labels.

Example:

```text
Bengali patient phrase
→ original transcript preserved
→ normalized concept: DYSPNEA
→ physician-facing label: Shortness of breath
```

Never discard the original patient wording solely because normalization exists.

## 10. Clinical data ownership

The system can produce:
- patient-reported data;
- machine-normalized data;
- document-extracted data;
- machine-generated draft summary.

Only clinician-reviewed/confirmed data should be presented as confirmed clinical record within the prototype.

## Phase 2 implemented prototype content

Five standard patient-selected flows are now active under the single authoritative `ai/complaint_flows/` system: chest pain, abdominal pain, fever, headache and cough/breathlessness. Pain histories cover site, onset/duration, character, radiation with a conditional location follow-up, associated symptoms, timing, aggravating/relieving factors and reported 0–10 severity. Other flows collect complaint-appropriate prototype details, including measured temperature/travel and sputum/activity impact.

Standard flows then collect branched medical, surgical, medication, allergy, family, personal and other-symptom history. Diabetes, surgery, medicines, allergies and other positive answers enable follow-ups. Unknown and not-reported remain explicit; absence is never inferred from missing or inactive responses.

The separate `ayush_demo.history` namespace contains eleven self-report prompts corresponding to the scoped AYUSH categories. These prompts only record what a person already knows or has been told; they do not calculate constitution, assess categories, classify disease or recommend interventions.

The original draft JSON contained obvious mixed-script/garbled translations and was replaced. All current English, Bengali and Hindi content is still **prototype/unvalidated** and marked in the kiosk. No clinical translation validation is claimed. Clinical review and language review are required before real use. Numeric input bounds and severity controls are form validation only; no diagnostic, treatment or red-flag/safety logic is implemented in this phase.

## Phase 3A normalization limits

A deterministic mock now recognizes thirteen symptom/qualitative concepts across English/Bengali/Hindi using 45 explicit fixtures. The ten symptom concepts correspond to the requested complaint vocabulary; three qualitative pain descriptions are additional fixtures. No diagnoses, medicines, treatment recommendations, broad NLP or automatic flow switching are implemented.

This is exact fixture matching, not medically validated translation. Negated/contextual/combined or unmatched phrases remain unrecognized. Explicit uncertainty is retained; unknown never becomes a positive concept. Mock confidence is null because a statistical confidence estimate is not available. Machine labels remain unverified after doctor summary confirmation.

Field context and source provenance must remain attached: a symptom mention in family/allergy history must not be reinterpreted downstream as the patient's current symptom. AYUSH remains excluded from normalization and diagnostic interpretation. Existing localized questions remain the authoritative patient UI text.

## Phase 3B clinical normalization scope & boundaries

Phase 3B brings `google/gemma-4-31b-it` via NVIDIA NIM into the normalization architecture with explicit clinical boundaries:

1. **Extraction Only, Never Diagnosis**:
   - Patient says: "chest pain" → Concept: `CHEST_PAIN`.
   - Forbidden: "chest pain" → `MYOCARDIAL_INFARCTION`.
   - Forbidden: "fever + cough" → `PNEUMONIA`.
   - Forbidden: "headache" → `MIGRAINE`.
   - No diagnostic inference, medication prescription, or treatment recommendations are permitted.

2. **Explicit Negation (Polarity)**:
   - "I do not have chest pain." → Concept: `CHEST_PAIN`, `polarity: "absent"`, `certainty: "certain"`.
   - "আমার শ্বাসকষ্ট নেই।" → Concept: `DYSPNEA`, `polarity: "absent"`, `certainty: "certain"`.
   - "मुझे सांस लेने में तकलीफ नहीं है।" → Concept: `DYSPNEA`, `polarity: "absent"`, `certainty: "certain"`.
   - Denied symptoms are explicitly tagged as absent, never encoded as unrecognized or converted into positive findings.

3. **Explicit Uncertainty**:
   - "I think I sometimes have chest pressure." → Concept: `PRESSURE_LIKE_PAIN`, `polarity: "present"`, `certainty: "uncertain"`.
   - Ambiguous or tentative language retains `certainty: "uncertain"`.
   - Confidence remains strictly `null` (the model is prohibited from fabricating statistical percentages like 0.92 or 87%).

4. **Vocabulary Invariance**:
   - The model must use only concepts from the authoritative Phase 3A ontology (`CHEST_PAIN`, `ABDOMINAL_PAIN`, `HEADACHE`, `FEVER`, `COUGH`, `DYSPNEA`, `NAUSEA`, `VOMITING`, `SWEATING`, `DIZZINESS`, `PRESSURE_LIKE_PAIN`, `SHARP_PAIN`, `BURNING_PAIN`).
   - Dynamic additions to the concept ontology are rejected by strict Pydantic validation.

5. **Linguistic Scope & Status**:
   - Initial prototype coverage: English, Bengali, Hindi.
   - All fixture cases are synthetic prototype evaluation cases; no claim of clinical or general linguistic validation is made.

