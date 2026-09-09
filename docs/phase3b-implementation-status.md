# Phase 3B Implementation and Verification Report — 2026-09-09

## Executive Summary

Phase 3B integrates NVIDIA Build / NVIDIA NIM hosted inference (`google/gemma-4-31b-it`) as the first real clinical normalization provider behind the provider-neutral boundary established in Phase 3A.

The integration strictly preserves the core architectural principle: **The deterministic InterviewEngine remains authoritative.** Gemma-4-31B never selects questions, branches, detects red flags, diagnoses, or prescribes; it performs constrained clinical language normalization only.

All automated acceptance criteria (backend tests on PostgreSQL and SQLite, frontend component tests, ESLint/Prettier/TypeScript checks, database migration continuity, secret audit, process restart persistence) pass completely. Empirical live diagnostics against `https://integrate.api.nvidia.com/v1` were conducted, analyzed, and documented honestly.

---

## 1. NVIDIA Provider Architecture

The integration implements the `ClinicalNormalizationProvider` protocol behind the Phase 3A provider boundary:

```text
InterviewEngine
    ↓
raw patient answer persisted (atomic transaction)
    ↓
NormalizationService (savepoint isolated)
    ↓
ClinicalNormalizationProvider interface
    ├── mock (deterministic offline catalog)
    └── nvidia (NvidiaClinicalNormalizationProvider)
    ↓
strict application validation (LiveProviderResult Schema 1.1)
    ↓
normalization_results (PostgreSQL snapshot with full provenance)
    ↓
structured clinical history (Fact.normalization)
    ↓
doctor view (separately displayed, labeled 'not clinician verified')
```

- **Adapter Module**: `backend/app/services/nvidia_normalization.py`
- **Provider Name**: `nvidia`
- **Provider Version**: `1.0.0`
- **HTTP Client**: Uses `httpx2` (the locked project HTTP library) with explicit transport timeout, non-redirecting transport (`follow_redirects=False`), and a 64KB byte stream cap to prevent memory exhaustion attacks.
- **Strict JSON Parsing**: `strict_json()` rejects duplicate JSON keys and nonstandard numeric constants without heuristic auto-repair.

---

## 2. Model & Endpoint Configuration

- **Inference Endpoint**: `POST https://integrate.api.nvidia.com/v1/chat/completions`
- **Hosted Model**: `google/gemma-4-31b-it`
- **Prompt Version**: `nvidia-1.0` (`ai/prompts/clinical_normalization_nvidia_v1.md`)
- **Sampling Parameters**:
  - `temperature`: `0` (conservative, deterministic)
  - `stream`: `false` (inference is non-streaming; transport streams to cap bytes)
  - `max_tokens`: `768` (constrained output budget, validated between 128 and 1536)
  - `chat_template_kwargs`: `{"enable_thinking": false}` (disables reasoning tokens)
- **Environment Configuration**:
  - `CLINICAL_NORMALIZATION_PROVIDER`: `mock` | `nvidia` | `disabled`
  - `NVIDIA_API_KEY`: Read from environment only; stored as Pydantic `SecretStr(exclude=True, repr=False)`
  - `NVIDIA_BASE_URL`: `https://integrate.api.nvidia.com/v1`
  - `CLINICAL_NORMALIZATION_MODEL`: `google/gemma-4-31b-it`
  - `CLINICAL_NORMALIZATION_TIMEOUT_SECONDS`: `8.0` (default for NVIDIA) to `15.0` seconds
  - `CLINICAL_NORMALIZATION_MAX_TOKENS`: `768`

Offline development, unit tests, and CI default to `CLINICAL_NORMALIZATION_PROVIDER=mock`, which runs completely offline without any API key.

---

## 3. Supported Structured-Output Mode & Verification

A dedicated capability probe (`scripts/check-nvidia-capabilities.py`) tested hosted capabilities:
1. `GET https://integrate.api.nvidia.com/v1/models` succeeds with HTTP 200 and confirms `google/gemma-4-31b-it` is listed.
2. Unauthenticated and invalid-key requests immediately return HTTP 401 in ~0.35s.
3. Unknown models return HTTP 404; deprecated models return HTTP 410.
4. **Structured Output Strategy**: Because hosted NIM endpoints vary in support for native JSON schema flags, the implementation relies on **tightly instructed prompt JSON generation + strict Pydantic application validation (`LiveProviderResult`)**. Application validation is the sole authority; model output is treated as untrusted input.

---

## 4. Output Contract & Schema 1.1

Live extraction operates under Schema 1.1:

```python
class LiveProviderFact(ProviderFact):
    polarity: Literal["present", "absent"]
    confidence: None

class LiveProviderResult(ProviderResult):
    schema_version: Literal["1.1"]
    canonical_field: str
    language: Language
    status: Literal["normalized", "unrecognized", "unknown"]
    facts: list[LiveProviderFact]
```

Key validation rules:
- **Polarity**: Required explicit `"present"` or `"absent"`. Denied symptoms must be `"absent"`.
- **Certainty**: Required `"certain"` or `"uncertain"`. Tentative language remains `"uncertain"`.
- **Confidence**: Must be `None`. Gemma-4-31B is strictly prohibited from inventing statistical probabilities (e.g. 0.92).
- **Evidence**: Must be an exact contiguous substring of the patient's raw text.
- **Concept Catalog**: Must belong to the authoritative Phase 3A vocabulary (`CHEST_PAIN`, `ABDOMINAL_PAIN`, `HEADACHE`, `FEVER`, `COUGH`, `DYSPNEA`, `NAUSEA`, `VOMITING`, `SWEATING`, `DIZZINESS`, `PRESSURE_LIKE_PAIN`, `SHARP_PAIN`, `BURNING_PAIN`). Any dynamic model additions or inferred diagnoses (e.g. `MYOCARDIAL_INFARCTION`) fail validation and produce `status: unavailable`, `reason: invalid_result`.

---

## 5. Privacy & Data Minimization

- **Input Minimization**: Only `text`, `language`, and `canonical_field` are transmitted.
- **Excluded Context**: Patient name, demo ABHA ID, hospital token, doctor identity, session history, and database IDs are completely stripped.
- **Secret Protection**: `NVIDIA_API_KEY` is wrapped in Pydantic `SecretStr`. It is never serialized, logged, returned by `/api/config` or any other route, or committed.
- **Audit Verification**: `python .runtime/audit-phase3b-secrets.py` scanned all 156 code, test, documentation, and log files in the repository and confirmed **0 key matches**.

---

## 6. Fault Tolerance & Persistence Behavior

The patient's answer commits atomically before normalization:
- If NVIDIA fails, times out, or returns invalid schema:
  - Raw patient answer remains committed and untouched.
  - Normalization records an explicit `unavailable` result with the specific reason:
    - `"timeout"` (exceeded timeout budget)
    - `"network_error"` (DNS, connection reset)
    - `"authentication_failed"` (HTTP 401/403)
    - `"rate_limited"` (HTTP 429)
    - `"server_error"` (HTTP 5xx)
    - `"invalid_result"` (malformed JSON, duplicate keys, schema violation)
  - Interview continues uninterrupted.
  - **No silent fallback to mock**: The system never fakes a success by quietly substituting mock data.

---

## 7. Empirical Live Evaluation Results

An opt-in evaluation script (`scripts/evaluate-nvidia-normalization.py`) was executed with `--run-live` against `https://integrate.api.nvidia.com/v1` for `google/gemma-4-31b-it`:

- **Gateway Connectivity**: `GET /v1/models` returned HTTP 200 in 0.18s; token authentication succeeded.
- **Inference Latency & Upstream Status**: Live POST requests to `https://integrate.api.nvidia.com/v1/chat/completions` for `google/gemma-4-31b-it` experienced an upstream `ReadTimeout` (>30s) on NVIDIA's hosted cluster.
- **Fault-Tolerant Handling**: The application cleanly caught the timeout, logged zero secrets or PHI, preserved the raw synthetic answers in PostgreSQL, recorded an immutable `status: unavailable`, `reason: timeout` normalization record with full provenance, and allowed the interview and doctor review to complete normally.
- **Transparency**: Real status is reported honestly; no simulated live success is claimed.

---

## 8. Verification Results

| Check | Result |
|---|---|
| Backend SQLite test suite | **214 passed** (159 Phase 1/2/3A + 55 Phase 3B contract/adversarial tests) |
| Backend PostgreSQL test suite | **214 passed** |
| Frontend Vitest component suite | **36 passed** (including normalization UI, polarity, unverified badges) |
| Chromium E2E browser suite | **7 passed** |
| Process restart persistence | **Passed**; PIDs changed; sessions, answers, normalization, and confirmations preserved |
| Post-restart browser resume checks | **2 passed** |
| TypeScript / production build | **Passed** (`tsc -b && vite build` clean) |
| ESLint | **Passed** with 0 warnings |
| Prettier | **Passed** |
| Ruff | **Passed** |
| Database migrations | **Passed**; empty, Phase 1, Phase 2, Phase 3A, and app DB upgrades clean; row hashes unchanged |
| Alembic schema comparison | **Clean**; no new upgrade operations detected |
| Secret audit | **Passed**; zero API key leakage across 156 files |

---

## 9. Known Limitations

1. **Upstream Hosted NIM Latency**: The hosted `google/gemma-4-31b-it` model on `integrate.api.nvidia.com` intermittently experiences severe upstream latency or cold-start timeouts (>30s). The application handles this fault-tolerantly by design.
2. **Prototype Clinical Scope**: Normalization maps directly stated symptoms to 13 canonical concepts across English, Bengali, and Hindi. Broad NLP, general translation, medication extraction, and autonomous diagnosis remain excluded.
3. **No Automatic Backfill**: Historical or confirmed records are never reprocessed when provider configuration changes.
4. **Deferred Roadmap Features**: Voice (ASR/TTS), red flags, document OCR, FHIR export, and production authentication remain scheduled for later phases.

---

## 10. Files Changed in Phase 3B

- **Backend Provider & Schemas**:
  - `backend/app/services/nvidia_normalization.py`
  - `backend/app/services/normalization_provider.py`
  - `backend/app/services/normalization.py`
  - `backend/app/schemas/normalization.py`
  - `backend/app/main.py`
  - `backend/requirements.txt`, `backend/requirements.lock`
- **Prompts & Ontology**:
  - `ai/prompts/clinical_normalization_nvidia_v1.md`
  - `ai/normalization/nvidia_evaluation.json`
- **Frontend Components & Types**:
  - `frontend/src/api/interview.ts`
  - `frontend/src/components/doctor/NormalizationPanel.tsx`
  - `frontend/src/i18n/normalization.ts`
  - `frontend/e2e/require-mock.ts`
- **Tests**:
  - `backend/tests/test_nvidia_normalization.py`
  - `frontend/src/test/normalization.test.tsx`
- **Scripts & Operations**:
  - `scripts/check-nvidia-capabilities.py`
  - `scripts/evaluate-nvidia-normalization.py`
  - `scripts/verify-phase3b-migrations.py`
  - `scripts/verify-restart.ps1`
  - `.runtime/audit-phase3b-secrets.py`
- **Documentation**:
  - `docs/decisions.md` (ADR-017)
  - `docs/architecture.md`
  - `docs/data-model.md`
  - `docs/api-contract.md`
  - `docs/clinical-scope.md`
  - `docs/testing.md`
  - `docs/security-privacy.md`
  - `docs/prompting.md`
  - `docs/roadmap.md`
  - `docs/requirements-traceability.md`
  - `docs/memory.md`
  - `docs/phase3b-implementation-status.md`
  - `docs/implementation-status.md`
