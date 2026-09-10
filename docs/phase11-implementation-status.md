# Phase 11 implementation status — 2026-09-10

Phase 11 is implemented for the **local prototype**. It establishes standards-based interoperability with India's **Ayushman Bharat Digital Mission (ABDM)** National Health Stack (M1, M2, M3) and **Hospital Information Systems (HIS / EMR)**, enabling end-to-end electronic health record exchange.

## Implemented Architecture & Workflow

```text
Patient Kiosk (Identify Step)
├── ABHA Input & Inline Quick "Verify" Action (M1)
└── Linked ABHA Profile (demo_abha_id / verified status)
              │
              ▼
Doctor Workspace / Patient Banner
├── Button: "🏥 ABDM & HIS"
│     └── ABDMHISModal
│           ├── ABDM (M1/M2) Card:
│           │     ├── ABHA Status (Mock Verified / Unverified)
│           │     ├── "Verify / Link ABHA" (OTP / Demographic Mock)
│           │     └── "Link Care Context (M2)" (Links OPD consultation to ABHA)
│           └── HIS Interoperability Card:
│                 ├── HIS Dispatch Status (Not Dispatched / Dispatched)
│                 ├── Target HIS Gateway (Local Simulated HIS / Configured URL)
│                 └── "📤 Dispatch to Hospital HIS"
│                       └── Bundles Phase 10 FHIR R4 Document + Intake Record
│
              │
              ▼
Backend Services & APIs (`/api/doctor/sessions/{id}/abdm/*`, `/api/doctor/sessions/{id}/his/*`)
├── ABDMService:
│     ├── verify_abha(session_id, abha_input, method)
│     ├── link_care_context(session_id, user)
│     └── get_abdm_status(session_id)
├── HISService:
│     ├── dispatch_to_his(session_id, user, target_system)
│     └── get_status(session_id)
└── Database Model: ABDMRecord (`abdm_records` table, migration 8b4e9c2d1f73)
      ├── session_id, patient_id
      ├── abha_number, abha_address, abha_status
      ├── care_context_reference, care_context_display, care_context_status, care_context_linked_at
      ├── his_dispatch_status, his_dispatch_receipt, his_dispatched_at
      └── consent_artefact_id
```

## Key Capabilities Delivered

### 1. ABDM Milestone 1 (M1): ABHA Identity & Verification
- **Validation Engine (`ABDMService._is_valid_abha`)**:
  - Validates 14-digit ABHA numbers (e.g. `91-1234-5678-9012` or `12345678901234`).
  - Validates ABHA phr handles (e.g. `patient@abdm`, `user@sbx`).
- **Sandbox Mock Verification (`verify_abha` & `verify_standalone_abha`)**:
  - Simulates OTP / demographic matching, generating a standardized `ABDMProfile` (Name, Gender, DOB, Masked Phone).
  - Updates `Patient.demo_abha_id` and persists status (`mock_verified`) in `ABDMRecord`.
  - Appends `ABHA_VERIFIED` to the session audit trail.

### 2. ABDM Milestone 2 (M2): HIP Care Context Linking
- **Care Context Generator (`link_care_context`)**:
  - Creates deterministic Care Context Reference: `medikiosk_ctx_<session_prefix>`.
  - Attaches human-readable label: `MediKiosk OPD Intake - Token <token>`.
  - Updates `care_context_status = "linked"` and records UTC timestamp `care_context_linked_at`.
  - Appends `ABDM_CARE_CONTEXT_LINKED` to the session audit trail with clinician actor provenance.

### 3. ABDM Milestone 3 (M3) & HIS Interoperability
- **Outbound HIS Dispatch Engine (`HISService.dispatch_to_his`)**:
  - Dynamically synthesizes the full Phase 10 HL7 FHIR R4 Document Bundle (`Composition` with LOINC `34105-7`, `Patient`, `Encounter`, `Condition`, `MedicationStatement`, `Observation`).
  - Transmits payload to configured `HIS_ENDPOINT_URL` or local simulated hospital gateway.
  - Generates verifiable receipt identifier: `HIS-ACK-<date>-<hash>`.
  - Stores receipt JSON in `abdm_records.his_dispatch_receipt` and updates status to `dispatched`.
  - Appends `HIS_DISPATCHED` to the session audit trail.

### 4. Dedicated Persistence & Database Migration
- **Schema Migration (`8b4e9c2d1f73_phase11_abdm_his.py`)**:
  - Created `abdm_records` table with foreign keys to `sessions.id` (CASCADE) and `patients.id`.
  - Applied cleanly to running PostgreSQL daemon and verified with SQLite.
  - Verified with `alembic check` (0 model drift).

### 5. Frontend Doctor Hub & Kiosk Integration
- **`ABDMHISModal.tsx`**:
  - Accessible via **"🏥 ABDM & HIS"** button in Doctor Workspace patient banner (`data-testid="abdm-his-btn"`).
  - M1 Card: ABHA status badge (`✓ Verified (Sandbox Mock)` vs `⚠️ Unverified`), inline verification form with demo buttons.
  - M2 Card: Care context reference, link button (`data-testid="link-care-context-btn"`), linked status pill.
  - HIS Interoperability Card: OPD dispatch status (`✓ Dispatched & Acknowledged` vs `Not Dispatched`), target system input, dispatch button (`data-testid="dispatch-his-btn"`), receipt preview.
  - Prominent Sandbox Demonstration disclaimer banner.
- **Kiosk Onboarding Integration (`frontend/src/routes/kiosk/index.tsx`)**:
  - Inline **"Verify"** button (`data-testid="kiosk-verify-abha-btn"`) on the `identify` step.
  - Instant demographic verification preview badge (`✓ ABHA Verified (Sandbox): <Name>`).

## Verification & Test Results

### 1. Backend Verification
- **Total Tests**: **350 passed** (0 failed, 1 warning) in 28.29s.
- **Phase 11 Integration Tests (`backend/tests/test_abdm_his.py`)**:
  - `test_abdm_verify_standalone_abha`: Validates format checking (invalid rejected, 14-digit and `@abdm` accepted with mock profile). (PASSED)
  - `test_abdm_session_verify_and_status`: Validates session ABHA verification, patient sync, and status endpoint. (PASSED)
  - `test_abdm_care_context_linking`: Validates M2 care context reference generation and status transitions. (PASSED)
  - `test_his_dispatch_with_fhir_document`: Validates FHIR Document bundle generation, dispatch receipt, and `HIS_DISPATCHED` audit log. (PASSED)
  - `test_abdm_his_authorization`: Validates unauthorized requests fail closed with HTTP 401. (PASSED)
- **Linting (`ruff check backend`)**: All checks passed with 0 errors, 0 warnings.

### 2. Frontend Verification
- **Unit & Component Tests (`vitest`)**: **84 passed** across 11 test files.
- **Phase 11 Component Tests (`frontend/src/test/phase11.test.tsx`)**:
  - `fetches and renders ABDM and HIS status when opened`: Verifies modal header, badges, and layout. (PASSED)
  - `handles ABHA verification via mock gateway`: Verifies form submission, mock verification API call, and success badge. (PASSED)
  - `links care context (M2)`: Verifies link button click, care context reference, and linked badge. (PASSED)
  - `dispatches to hospital HIS and renders receipt`: Verifies dispatch action, receipt reference display, and status update. (PASSED)
  - `calls onClose when close button is clicked`: Verifies modal dismissal. (PASSED)
- **Linting (`npm run lint`)**: 0 errors, 0 warnings.
- **TypeScript Build (`npm run build`)**: Clean build, 0 type errors.

## Invariant Adherence Matrix

| Invariant | Status | Mechanism |
|-----------|--------|-----------|
| **National Health Stack (ABDM)** | ✅ Preserved | M1 ABHA validation/verification, M2 HIP care context linking, M3 electronic health data exchange. |
| **FHIR Document Integration** | ✅ Preserved | Outbound HIS dispatch packages Phase 10 HL7 FHIR R4 Document Bundle (LOINC `34105-7`). |
| **Strict Non-Diagnostic Boundary** | ✅ Preserved | Exported and dispatched conditions remain provisional; no autonomous diagnoses or treatments are asserted. |
| **Consent Invariant** | ✅ Preserved | Doctor inspection and HIS dispatch require active patient sharing consent (`Consent.share_with_doctor == True`). |
| **Staff Authorization** | ✅ Preserved | `/api/doctor/sessions/{id}/abdm/*` and `/api/doctor/sessions/{id}/his/*` require server-authenticated doctor context. |
| **Session Audit Trail** | ✅ Preserved | `ABHA_VERIFIED`, `ABDM_CARE_CONTEXT_LINKED`, and `HIS_DISPATCHED` logged with actor provenance. |
| **Dedicated Persistence** | ✅ Preserved | `abdm_records` table with migration `8b4e9c2d1f73`; 0 Alembic drift. |
| **Sandbox Transparency** | ✅ Preserved | Prominently labeled as *"ABDM Sandbox Demonstration (Non-Production / Synthetic Gateway)"*. |
