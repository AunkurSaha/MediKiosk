# AI Prompting Guidelines — MediKiosk

This document applies once LLM integration is introduced.

## 1. General rule

The model receives **minimum necessary structured context** and must return structured output.

Do not make one giant prompt responsible for interview, safety, extraction, diagnosis, summary, and translation.

Separate tasks.

## 2. Clinical normalization prompt

Purpose:
- convert patient free text into known structured concepts.

Requirements:
- preserve meaning;
- do not infer diagnosis;
- do not invent missing fields;
- use explicit `null`/unknown;
- retain original text separately outside the model output.

Conceptual output:
```json
{
  "concepts": [
    {
      "field": "hpi.associated_symptoms.dyspnea",
      "value": true,
      "confidence": 0.93
    }
  ]
}
```

## 3. Document extraction prompt

Input:
- OCR text;
- optional document type;
- schema.

Requirements:
- extract only facts present;
- include source spans/line references when feasible;
- include confidence;
- do not autocorrect uncertain medicine names into certainty;
- no treatment advice.

## 4. Summary prompt

Input:
- structured clinical history;
- verified/unverified document facts;
- alerts;
- discrepancies.

Prompt requirements:
- “Generate a physician-review draft.”
- “Do not diagnose.”
- “Do not prescribe.”
- “Do not invent.”
- “Use only supplied facts.”
- “Mark unavailable information as not reported/unknown.”
- “Clearly preserve uncertainty.”

## 5. Model output handling

Always:
1. call provider through adapter;
2. parse structured response;
3. validate with Pydantic;
4. reject/repair invalid schema in controlled logic;
5. record provider/model metadata if clinically relevant;
6. never silently promote output to verified fact.

## 6. Prompt location

Keep version-controlled prompts under:
- `ai/prompts/`

Each production-used prompt should have:
- stable name;
- version;
- purpose;
- input schema;
- output schema;
- tests/fixtures when practical.

## Phase 3A executable boundary and future prompt

The active phase uses no LLM and no live prompt. The future contract is [clinical_normalization_v1.md](../ai/prompts/clinical_normalization_v1.md); its strict ProviderInput/ProviderResult schemas are implemented in backend/app/schemas/normalization.py. The conceptual example above is target guidance, not the current wire contract.

Use only the supplied field/language/text/minimal context; reject unrelated output keys, diagnoses/treatments, unsupported concepts, missing evidence and invalid confidence. Retain negation, uncertainty, subject/context and raw source wording; unrecognized/unknown outputs contain no facts. Patient text is data, not instructions. The backend assigns canonical display/value from its allowlist catalog and owns source IDs, provider metadata and verification labels. Output never changes interview flow, consent or confirmation.

No fake confidence is assigned by the mock. Future adapters must use cancellable async I/O and transport timeouts in addition to the service timeout. Deterministic fallback must preserve the interview. Do not enable an external provider until a later explicit provider/data-handling decision.

## Phase 3B NVIDIA NIM prompt implementation

Phase 3B implements and validates the active prompt in `ai/prompts/clinical_normalization_nvidia_v1.md` (version `nvidia-1.0`):

- **System Role**:
  `You are a clinical-language normalization component. Prompt version: nvidia-1.0.`
  `Map only directly stated patient language to the supplied allowed clinical concepts.`
- **Untrusted Input Separation**:
  Patient text is strictly separated from system instructions as a JSON object payload (`{"text": "...", "language": "...", "canonical_field": "..."}`).
- **Explicit Negative Constraints**:
  - Do not diagnose, prescribe, recommend treatment, infer diseases from symptoms or invent facts.
  - Do not select interview questions, branch, complete an interview, change consent, trigger safety alerts or confirm clinical records.
- **Polarity & Negation**:
  - Directly denied symptoms MUST produce `polarity: "absent"`, never `present`.
- **Uncertainty & Confidence**:
  - Ambiguous or tentative language MUST produce `certainty: "uncertain"`.
  - Confidence MUST remain `null`; hallucinated probabilities (e.g. 0.92) are forbidden.
- **Exact Evidence Matching**:
  - `evidence` must be an exact contiguous substring of the untouched input text.
- **Context Preservation**:
  - `canonical_field` provides section context; family or past history must not be promoted to active symptoms.
- **Schema 1.1 Specification**:
  - Follows `LiveProviderResult` schema appended dynamically to system prompt instructions.

