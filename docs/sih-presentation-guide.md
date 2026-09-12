# MediKiosk — Smart India Hackathon (SIH) Presentation & Project Guide

**Current as of:** September 2026  
**Project Stage:** Complete Functional Local Prototype (Phase 1–12 Architecture Implemented); Not a production clinical diagnostic device.  
**Target Repository:** `c:\MEDIKIOSK`

---

## Quick Navigation for Presenters

- [1. Executive Summary & Problem Statement](#1-executive-summary--problem-statement)
- [2. Quickstart: How to Run the Demo on Presentation Day](#2-quickstart-how-to-run-the-demo-on-presentation-day)
- [3. Non-Negotiable Clinical Boundaries & AI Governance](#3-non-negotiable-clinical-boundaries--ai-governance)
- [4. High-Level Architecture & Data Flow](#4-high-level-architecture--data-flow)
- [5. How Everything Works Under the Hood (The 7 Core Engines)](#5-how-everything-works-under-the-hood-the-7-core-engines)
- [6. End-to-End User Workflows (Patient, Doctor, Triage)](#6-end-to-end-user-workflows-patient-doctor-triage)
- [7. Complete Technology Stack](#7-complete-technology-stack)
- [8. Repository Map: What Exists in Which Part of the Codebase](#8-repository-map-what-exists-in-which-part-of-the-codebase)
- [9. Feature Status Matrix: What is Working vs. What Remains](#9-feature-status-matrix-what-is-working-vs-what-remains)
- [10. Roadmap to Hospital Production Deployment](#10-roadmap-to-hospital-production-deployment)
- [11. Verification Evidence & Test Metrics](#11-verification-evidence--test-metrics)
- [12. 6-to-8 Minute SIH Live Stage Demo Script](#12-6-to-8-minute-sih-live-stage-demo-script)
- [13. SIH Judge Q&A Defense Battlecard](#13-sih-judge-qa-defense-battlecard)
- [14. One-Slide Pitch Summary](#14-one-slide-pitch-summary)

---

## 1. Executive Summary & Problem Statement

### The Problem in Indian Outpatient Departments (OPD)
In high-volume Indian government and district hospitals, an outpatient doctor often attends to **60 to 100+ patients per session**. The average consultation time is often **under 3 minutes**. During this brief window, clinicians struggle with:
1. **Multilingual barriers:** Patients describe symptoms in regional languages and colloquial vernacular.
2. **Fragmented, crumpled paper records:** Patients carry torn prescriptions, hand-written slips, and lab reports from multiple facilities, making longitudinal timeline synthesis nearly impossible.
3. **Repetitive clerical intake:** Doctors waste over 50% of the consultation asking basic routine questions and typing history instead of examining the patient.
4. **Risk of missed critical red flags:** Life-threatening cardiovascular or respiratory red flags can be lost in crowded OPD waiting queues.

### MediKiosk's Solution
**MediKiosk is an AI-assisted, multilingual pre-consultation clinical intake kiosk and triage system.**

While waiting in the OPD queue, the patient interacts with a digital kiosk (via touch or native voice in English, Bengali, or Hindi). MediKiosk:
- Collects structured chief complaints through adaptive clinical branching.
- Digitizes past paper prescriptions and lab reports via OCR.
- Continuously screens for emergency symptoms using deterministic, rule-based red flags.
- Reconciles past documents with current reported symptoms into a unified medical timeline.
- Generates a clinician-ready structured draft summary.
- Delivers the complete package to the doctor’s desk before the patient even enters the consultation chamber.
- Exports confirmed records directly into **HL7 FHIR R4** bundles compatible with the **Ayushman Bharat Digital Mission (ABDM)**.

> **Key Takeaway:** MediKiosk does **not** replace the doctor. It replaces the clerical burden of intake, giving doctors structured, verified data so they can focus on diagnosis and patient care.

---

## 2. Quickstart: How to Run the Demo on Presentation Day

### 2.1 Starting the System (Step-by-Step)

Open two PowerShell terminals on Windows:

#### Terminal 1: Start Backend (FastAPI + SQLite + Sarvam AI)
```powershell
cd c:\MEDIKIOSK
powershell -ExecutionPolicy Bypass -File scripts\start-backend-sqlite.ps1
```
*What this script does:*
- Sets `APP_ENV=test` and loads `.runtime/acceptance.sqlite`.
- Runs Alembic migrations (`alembic upgrade head`) to ensure schema is at latest version.
- Automatically seeds the demo clinician user into the database.
- Launches Uvicorn on `http://127.0.0.1:8010` with Sarvam AI API keys inherited from `.env`.
- Waits until `http://127.0.0.1:8010/api/health` returns HTTP 200 OK.

#### Terminal 2: Start Frontend (React + Vite)
```powershell
cd c:\MEDIKIOSK\frontend
npm run dev
```
*Frontend will launch on:* `http://127.0.0.1:5175`

---

### 2.2 Key URLs for Live Demonstration

| Destination | URL | Description |
|---|---|---|
| **Patient Login / Kiosk** | `http://127.0.0.1:5175/login` | Phone OTP login or 1-click Demo bypass |
| **Doctor Workspace** | `http://127.0.0.1:5175/doctor` | Clinician review, evidence timeline, summary & FHIR |
| **Triage Dashboard** | `http://127.0.0.1:5175/triage` | Live real-time emergency alert monitor (WebSocket) |
| **Interactive API Docs** | `http://127.0.0.1:8010/docs` | FastAPI Swagger UI showing all endpoints |
| **System Health & Config** | `http://127.0.0.1:8010/api/config` | Shows active providers (NVIDIA, Sarvam, Mock) |

---

### 2.3 Ready-to-Use Demo Credentials & Test Data

#### Phone OTP Login:
- **Phone Number:** `9876543210` (or any valid 10-digit Indian number)
- **Request OTP:** Click "Request OTP"
- **Fill OTP:** In demo mode, click the convenient **"Auto-fill Test OTP"** button (or check `GET /api/v1/auth/dev/last-otp?phone_number=+919876543210`).
- **Speed Shortcut:** On the login page, you can also click **"Quick Patient Demo"** or **"Quick Doctor Demo"** for instant 1-click access during time-constrained presentations!

#### Sample Files for Document Upload Demonstration:
Pre-made synthetic test documents are stored in `ai/document_fixtures/`:
1. `c:\MEDIKIOSK\ai\document_fixtures\prescription.png` — Synthetic Indian OPD prescription (extracts Metformin, Atorvastatin, dosages, instructions).
2. `c:\MEDIKIOSK\ai\document_fixtures\lab_report.png` — Synthetic lipid and metabolic panel (extracts HbA1c, Fasting Blood Glucose, flagged high values).

---

## 3. Non-Negotiable Clinical Boundaries & AI Governance

MediKiosk is engineered strictly adhering to clinical safety rules defined in [AGENTS.md](file:///c:/MEDIKIOSK/AGENTS.md):

```text
       ┌──────────────────────────────────────────────────────────┐
       │                   UNSTRUCTURED INPUT                     │
       │    (Patient Voice, Touch Wording, Uploaded Documents)    │
       └────────────────────────────┬─────────────────────────────┘
                                    │
                                    ▼
       ┌──────────────────────────────────────────────────────────┐
       │                 STRUCTURED CLINICAL DATA                 │
       │     (Normalized concepts, typed schemas, provenance)     │
       └────────────────────────────┬─────────────────────────────┘
                                    │
                                    ▼
       ┌──────────────────────────────────────────────────────────┐
       │            DETERMINISTIC SAFETY RULES ENGINE             │
       │    (Versioned JSON rules; NOT dependent on an LLM)       │
       └────────────────────────────┬─────────────────────────────┘
                                    │
                                    ▼
       ┌──────────────────────────────────────────────────────────┐
       │               CLINICAL DRAFT & PROVENANCE                │
       │     (Every extracted fact is visibly UNVERIFIED)         │
       └────────────────────────────┬─────────────────────────────┘
                                    │
                                    ▼
       ┌──────────────────────────────────────────────────────────┐
       │             HUMAN CLINICIAN IN THE LOOP                  │
       │      (Doctor edits, verifies fields, confirms summary)   │
       └────────────────────────────┬─────────────────────────────┘
                                    │
                                    ▼
       ┌──────────────────────────────────────────────────────────┐
       │                  IMMUTABLE FINAL RECORD                  │
       │        (Exported to HL7 FHIR R4 Bundle / ABDM)           │
       └──────────────────────────────────────────────────────────┘
```

### Golden Safety Rules:
1. **No Autonomous Diagnosis:** The AI never declares a diagnosis. UI copy never says *"You have X"*. It says: *"Patient reported chest pain radiating to left arm. Potential emergency symptoms detected. Immediate clinical assessment recommended."*
2. **No Prescription or Medication Changes:** The system never instructs a patient to start, stop, or change medications.
3. **Deterministic Safety Rules:** Red-flag emergency detection does **not** rely on generative LLM prompts. It is evaluated by a deterministic, auditable rule engine against versioned JSON rule sets.
4. **Structured Data is Ground Truth:** The source of truth is structured, validated database records—never raw conversational chat history or unparsed prose.
5. **Visible Verification Provenance:** Extracted OCR data is marked with confidence metrics and labeled as `Needs Verification`. It only becomes verified when explicitly confirmed by the licensed clinician.

---

## 4. High-Level Architecture & Data Flow

MediKiosk is built as a **Modular Monolith**—combining clean service-layer boundaries with high deployment simplicity (no Kubernetes or microservice orchestration overhead for rural hospital tiers):

```text
┌───────────────────────────────────────────────────────────────────────────┐
│                      FRONTEND (React 19 + Vite 8)                         │
│   /login (OTP)  │  /kiosk (Patient Intake)  │  /doctor  │  /triage        │
└─────────────────────────────────────┬─────────────────────────────────────┘
                                      │ REST API (JSON) + WebSocket Alerts
┌─────────────────────────────────────▼─────────────────────────────────────┐
│                      BACKEND (FastAPI + Pydantic v2)                      │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ API Endpoints: /auth, /sessions, /interview, /speech, /doctor, etc.  │  │
│  └──────────────────────────────────┬──────────────────────────────────┘  │
│                                     │                                     │
│  ┌──────────────────────────────────▼──────────────────────────────────┐  │
│  │ Core Service Layer:                                                 │  │
│  │  • AuthService & SmsProvider (OTP generation & verification)        │  │
│  │  • InterviewEngine & AdaptiveFlow (Deterministic clinical tree)     │  │
│  │  • SarvamSpeechService (ASR voice intake & TTS question readout)    │  │
│  │  • NormalizationService (NVIDIA NIM / Ontology concept mapping)     │  │
│  │  • RedFlagsEngine (Deterministic safety rule evaluation)            │  │
│  │  • DocumentService & SarvamOCR (Prescription/Lab entity extraction) │  │
│  │  • Timeline & DiscrepancyEngine (Longitudinal record reconciliation)│  │
│  │  • ClinicalSummaryService (Draft synthesis & immutable confirmation)│  │
│  │  • FHIRAdapterService (HL7 FHIR R4 & ABDM profile bundle generator) │  │
│  └──────────────────┬───────────────────────────────┬──────────────────┘  │
└─────────────────────┼───────────────────────────────┼─────────────────────┘
                      │                               │
                      ▼                               ▼
       ┌──────────────────────────────┐ ┌───────────────────────────────────┐
       │         PERSISTENCE          │ │        EXTERNAL ADAPTERS          │
       │  • PostgreSQL (Target)       │ │  • Sarvam AI (ASR, TTS, OCR)      │
       │  • SQLite (Local Fallback)   │ │  • NVIDIA NIM (Normalization)     │
       │  • SQLAlchemy 2 + Alembic    │ │  • ABDM / HIS Sandbox Connectors  │
       └──────────────────────────────┘ └───────────────────────────────────┘
```

---

## 5. How Everything Works Under the Hood (The 7 Core Engines)

### Engine 1: Authentication & Session Security Engine
- **Files:** [auth.py](file:///c:/MEDIKIOSK/backend/app/api/v1/auth.py), [auth_service.py](file:///c:/MEDIKIOSK/backend/app/services/auth_service.py), [sms_provider.py](file:///c:/MEDIKIOSK/backend/app/services/sms_provider.py)
- **How it works:**
  1. Patient submits a 10-digit mobile number.
  2. The phone number is normalized to E.164 standard (`+91XXXXXXXXXX`).
  3. A 6-digit cryptographic OTP is generated. The plaintext OTP is **never stored in the database**; only a salted SHA-256 hash is persisted alongside an expiration timestamp (5 minutes) and retry counter.
  4. Once verified, the server issues a secure, HTTP-only session cookie containing an encrypted JWT/session token.
  5. **Strict Multi-Tier Role-Based Access Control (RBAC):**
     - Three distinct roles: `patient`, `doctor`, and `triage`.
     - `patient`: Authenticated via phone OTP or patient demo login. Restricted strictly to `/kiosk/*` and own intake session (`session.patient_id == user.id`). Blocked from doctor workspaces, triage operational boards, clinical fact verification, and summaries.
     - `doctor`: Clinical staff. Access to `/doctor/*`, clinical verification, timeline reconciliation, summary confirmation, and FHIR/ABDM exports. Blocked from `/triage`.
     - `triage`: Emergency nursing staff. Access to `/triage` and live emergency red-flag feeds via single-use cryptographically validated WebSocket tickets (`ticket_type="triage_ws"`). Blocked from full doctor workspaces and patient intake.
     - Defense-in-depth: Enforced simultaneously via backend FastAPI dependencies (`require_doctor`, `require_triage`, `require_patient`) and frontend React route guards (`ProtectedRoute`), preventing data leakage even under direct URL navigation or manual HTTP manipulation.

### Engine 2: Adaptive Multilingual Clinical Intake Engine
- **Files:** [interview_engine.py](file:///c:/MEDIKIOSK/backend/app/services/interview_engine.py), [adaptive.py](file:///c:/MEDIKIOSK/backend/app/services/adaptive.py), `ai/complaint_flows/*.json`
- **How it works:**
  1. The patient chooses their preferred language: English (`en`), Bengali (`bn`), or Hindi (`hi`).
  2. The patient selects from 5 initial complaint families (Chest Pain, Abdominal Pain, Fever, Headache, Cough/Dyspnea) or the dedicated AYUSH demonstration flow.
  3. The engine uses a deterministic decision tree loaded from versioned JSON files.
  4. Questions adapt dynamically based on previous responses (e.g., if chest pain is selected, questions regarding radiation, onset, and breathlessness are activated).
  5. Missing or skipped questions are explicitly preserved as `NOT_REPORTED` or `UNKNOWN`—the system **never** assumes absence of a symptom without patient confirmation.

### Engine 3: Voice Interaction & Indian Speech AI Engine
- **Files:** [sarvam_speech.py](file:///c:/MEDIKIOSK/backend/app/services/sarvam_speech.py), [speech_provider.py](file:///c:/MEDIKIOSK/backend/app/services/speech_provider.py), [VoiceRecorder.tsx](file:///c:/MEDIKIOSK/frontend/src/components/kiosk/VoiceRecorder.tsx)
- **How it works:**
  1. Voice intake is strictly gated behind explicit patient consent.
  2. The frontend captures audio via the browser `MediaRecorder` API (WAV format, 16kHz).
  3. Audio is streamed to the backend and routed to **Sarvam AI ASR** (`saarika:v2` model) supporting Indian regional accents and code-switching (Hinglish/Bengali).
  4. The transcribed text is returned to the user as a **provisional candidate**. The user must visually review and confirm or edit the transcription before it is committed to the medical record.
  5. Questions can be read aloud using Sarvam AI Text-to-Speech (`bulbul:v1` model) with visible fallback to browser speech synthesis if offline.

### Engine 4: Clinical Concept Normalization Engine
- **Files:** [normalization.py](file:///c:/MEDIKIOSK/backend/app/services/normalization.py), [nvidia_normalization.py](file:///c:/MEDIKIOSK/backend/app/services/nvidia_normalization.py), `ai/ontology/concepts.json`
- **How it works:**
  1. Patient vernacular phrases (e.g., *"bukhe byatha"* in Bengali, *"chhati me jalan"* in Hindi) are mapped to a standardized clinical ontology (e.g., `CHEST_PAIN`, `RETROSTERNAL_DISCOMFORT`, `DYSPNEA`).
  2. This mapping is performed using an **NVIDIA NIM** LLM adapter or a deterministic rule dictionary.
  3. Strict schema guards prevent the model from hallucinating diagnoses; it can only tag extracted concepts from a pre-approved vocabulary whitelist.

### Engine 5: Deterministic Red-Flag Safety Screening Engine
- **Files:** [red_flags.py](file:///c:/MEDIKIOSK/backend/app/services/red_flags.py), [triage_notifier.py](file:///c:/MEDIKIOSK/backend/app/services/triage_notifier.py), [red_flags_v1.json](file:///c:/MEDIKIOSK/ai/safety_rules/red_flags_v1.json)
- **How it works:**
  1. After every answer submission, the structured intake payload is evaluated against deterministic safety rules.
  2. Example Rule (`RF-CHEST-001`): If `hpi.severity >= 8` AND `hpi.radiation == true`, trigger `Priority: Emergency`.
  3. The trigger is instantly broadcast via **WebSockets** to the `/triage` nursing dashboard.
  4. The alert payload includes: `rule_id`, `severity`, `triggering_facts`, `timestamp`, and `acknowledgement_state`.
  5. The patient sees an urgent prompt advising immediate physical attention, while nursing staff are alerted to triage the patient out of the queue.

### Engine 6: Document Intelligence & OCR Extraction Engine
- **Files:** [document_service.py](file:///c:/MEDIKIOSK/backend/app/services/document_service.py), [sarvam_ocr.py](file:///c:/MEDIKIOSK/backend/app/services/sarvam_ocr.py), [medical_extractor.py](file:///c:/MEDIKIOSK/backend/app/services/medical_extractor.py), [medical_facts.py](file:///c:/MEDIKIOSK/backend/app/services/medical_facts.py)
- **How it works:**
  1. Patients upload photos of past paper prescriptions or lab reports (JPEG, PNG, PDF; validated and stored securely).
  2. The file is processed via **Sarvam Document Intelligence OCR** to extract raw text and bounding boxes.
  3. The medical entity extractor parses:
     - **Medications:** Drug name, dosage, frequency, route.
     - **Laboratory Results:** Test name, measured value, unit, reference range, abnormal flags (`HIGH`, `LOW`).
  4. Every single extracted fact retains full **provenance metadata**: `source_document_id`, `page_number`, `bounding_box`, `extraction_confidence`, and `verification_status=unverified`.

### Engine 7: Longitudinal Timeline, Clinical Summary & Interoperability Engine
- **Files:** [timeline.py](file:///c:/MEDIKIOSK/backend/app/services/timeline.py), [discrepancies.py](file:///c:/MEDIKIOSK/backend/app/services/discrepancies.py), [clinical_summary.py](file:///c:/MEDIKIOSK/backend/app/services/clinical_summary.py), [fhir.py](file:///c:/MEDIKIOSK/backend/app/services/fhir.py), [abdm.py](file:///c:/MEDIKIOSK/backend/app/services/abdm.py), [his.py](file:///c:/MEDIKIOSK/backend/app/services/his.py)
- **How it works:**
  1. **Longitudinal Timeline:** Synthesizes patient-reported history with past digitized records into an interactive chronological timeline.
  2. **Discrepancy Detection:** Automatically flags contradictions (e.g., patient reported no known diabetes, but an uploaded prescription contains Metformin 500mg).
  3. **Draft Clinical Summary:** Synthesizes structured data into a concise, physician-ready SBAR (Situation, Background, Assessment, Recommendation) format.
  4. **Doctor Verification:** Clinicians can edit any field, verify or discard extracted facts, and confirm the record.
  5. **Immutability & Audit Trail:** Once confirmed, a record is cryptographically locked; subsequent modifications create versioned amendments with doctor credentials and timestamps.
  6. **Interoperability Standards:** Transforms confirmed data into **HL7 FHIR R4 Bundles** compliant with National Resource Centre for EHR in India (NRCES) profiles (`Composition`, `Patient`, `Condition`, `Observation`, `MedicationStatement`, `DocumentReference`). Demonstrates simulated **ABHA Care Context Linking** and **HIS dispatch**.

---

## 6. End-to-End User Workflows (Patient, Doctor, Triage)

### 6.0 Role-Based Access Control (RBAC) & Portal Authentication
MediKiosk enforces **hardened multi-role boundaries** at both the FastAPI backend dependency level and React client route level:
- **Patient Kiosk (`/login`):** Authenticates patients via **Phone Number + OTP**. Grants access exclusively to the self-guided patient intake flow (`/kiosk/*`). Patients are strictly blocked with `403 Forbidden` from viewing doctor queues, triage alerts, clinical summaries, or medical facts.
- **Portal Switcher:** On the patient login page, an explicit card (`👨‍⚕️ Clinical Specialist & Staff Portal`) allows clinicians and nursing staff to switch directly to `/staff/login` (also available via `/management/login`).
- **Unified Staff & Specialist Password Portal (`/staff/login`):** 
  - Allows healthcare staff (Doctors and Triage Nurses) to log in using their **10-digit Phone Number** (or E.164 / Staff ID) and secure **Password**.
  - Passwords are encrypted and verified using standard PBKDF2-HMAC-SHA256 (100,000 iterations).
  - Automatically redirects users to their designated workstation based on role:
    - `doctor` role ➔ `/doctor` (Physician Review Workspace)
    - `triage` role ➔ `/triage` (Emergency Red-Flag Nursing Board)
  - Features quick-fill demo chips for rapid stage demonstration:
    - Doctor: `9876500001` / `Doctor@123`
    - Triage: `9876500002` / `Triage@123`
  - Includes a prominent return link: `← Switch to Patient Kiosk Intake`.

### 6.1 Patient Journey (At the Kiosk)
```text
[1. OTP Login] ────► [2. Language: EN / BN / HI] ────► [3. Demographics & ABHA]
                                                                  │
[6. Voice / Touch] ◄─── [5. Adaptive Interview] ◄─── [4. Granular Consent]
        │
        ▼
[7. Red-Flag Check] ──► [8. Document Upload] ──► [9. Review & Submit]
```
1. **Login:** Patient inputs phone number and verifies with OTP.
2. **Language:** Selects English, Bengali, or Hindi. Entire interface, questions, and audio instantly localize.
3. **Identification:** Enters basic demographics; optionally enters 14-digit ABHA ID.
4. **Consent:** Three independent toggles: (a) Sharing with doctor, (b) Audio recording, (c) Document digitization.
5. **Complaint Selection:** Picks Chief Complaint (e.g., Chest Pain).
6. **Adaptive Intake:** Answers questions via touch steppers or native voice recording.
7. **Red-Flag Screening:** Continuous background safety check. If severe, emergency banner displays.
8. **Document Upload:** Snaps photo of previous prescription/lab report.
9. **Submission:** Reviews all answers on a confirmation screen and submits.

---

### 6.2 Doctor Journey (In the Consultation Room)
```text
[1. Doctor Portal] ──► [2. Select Patient Session] ──► [3. Review Evidence & Timeline]
                                                                    │
[6. Export FHIR / ABDM] ◄─── [5. Immutable Confirm] ◄─── [4. Verify Facts & Edit Summary]
```
1. **Workspace:** Doctor logs into `/doctor` and views the queue of completed intakes.
2. **Session Detail:** Opens patient session.
3. **Comprehensive Evidence View:**
   - Patient's verbatim quotes and translations.
   - Chronological timeline merging past records with current intake.
   - Highlighted discrepancies (e.g., medication conflicts).
   - Side-by-side view of uploaded original paper slips alongside extracted OCR facts.
4. **Field Verification:** Doctor clicks "Verify" or "Reject" on each extracted lab/medication fact.
5. **Summary Confirmation:** Doctor reviews the auto-drafted clinical brief, edits text as necessary, and clicks **"Confirm Summary"** (creates an immutable, audited record).
6. **ABDM / FHIR Export:** Doctor clicks "Export FHIR" to inspect the NRCES-compliant JSON bundle or trigger simulated ABDM Care Context Linking.

---

### 6.3 Triage Staff Journey (Nursing Station)
```text
[1. Open /triage] ──► [2. WebSocket Connection] ──► [3. Real-Time Red-Flag Alert Pops Up]
                                                                    │
                                            [4. Clinical Staff Acknowledges & Escalates]
```
1. Triage staff keep `http://127.0.0.1:5175/triage` open.
2. When a patient at the kiosk triggers a red-flag condition (e.g., severe radiating chest pain), a high-priority red alert immediately rings and flashes on the triage board via WebSockets.
3. The alert displays the patient's name, kiosk ID, triggering symptom facts, and time elapsed.
4. Triage nurse clicks "Acknowledge Alert" and immediately intercepts the patient from the waiting queue.

---

## 7. Complete Technology Stack

| Layer | Technology & Version | Purpose in MediKiosk |
|---|---|---|
| **Frontend Framework** | React 19, Vite 8, TypeScript 6 | Responsive, touch-optimized kiosk & clinician interfaces |
| **Styling & UI** | Tailwind CSS 4, Lucide Icons | Clean, modern glassmorphism aesthetic; high-contrast accessibility |
| **Client Routing & State** | React Router 7, React Context | Role-based route guards (`/kiosk`, `/doctor`, `/triage`, `/login`) |
| **Backend API** | Python 3.12, FastAPI, Uvicorn | High-performance asynchronous RESTful APIs & WebSockets |
| **Data Contracts** | Pydantic v2 | Strict schema validation for clinical data, OCR, and FHIR payloads |
| **ORM & Migrations** | SQLAlchemy 2, Alembic | Relational data modeling, version-controlled database schemas |
| **Production Database** | PostgreSQL + Psycopg 3 | Target production database for hospital deployments |
| **Local Demo Database** | SQLite (Strict Test/Demo Mode) | Zero-setup local runtime fallback ensuring local demo reliability |
| **Speech AI (ASR & TTS)** | Sarvam AI (`saarika:v2`, `bulbul:v1`) | Indian accented & regional voice transcription and question readout |
| **Document OCR** | Sarvam Document Intelligence API | Prescription and laboratory document digitization |
| **Clinical Normalization** | NVIDIA NIM / Custom Ontology Whitelist | Vernacular symptom normalization to clinical concepts without diagnosis |
| **Safety Rule Engine** | Pure Python + Versioned JSON | Deterministic, auditable red-flag symptom screening |
| **Interoperability** | HL7 FHIR R4 (NRCES / NDHM Profiles) | Indian ABDM-compliant clinical document bundle generation |
| **Unit & Integration Tests** | pytest, HTTPX (428 backend tests) | Backend security, API, workflow, and schema regression suites |
| **Frontend Tests** | Vitest, React Testing Library (104 tests)| Component rendering, language toggles, and state unit tests |
| **End-to-End E2E Tests** | Playwright with Chromium | Real browser end-to-end user journeys from login to doctor sign-off |
| **Code Quality** | Ruff, ESLint, Prettier, `tsc` | Strict PEP 8 and TypeScript static analysis |

---

## 8. Repository Map: What Exists in Which Part of the Codebase

```text
MEDIKIOSK/
├── frontend/                          # React + TypeScript Client Application
│   ├── src/
│   │   ├── App.tsx                    # Route definitions and role-based guards
│   │   ├── api/client.ts              # Typed API client with cookie auth & error handling
│   │   ├── context/AuthContext.tsx    # Global session & authentication state
│   │   ├── routes/
│   │   │   ├── login/index.tsx        # Phone OTP login, dev OTP auto-fill, demo shortcuts
│   │   │   ├── kiosk/                 # Patient intake wizard (Language, Consent, Intake, Upload)
│   │   │   ├── doctor/                # Doctor workspace (Patient Queue, Evidence, Summary)
│   │   │   └── triage/                # Live emergency alert dashboard with WebSockets
│   │   ├── components/
│   │   │   ├── kiosk/VoiceRecorder.tsx# Native audio recorder with Sarvam ASR integration
│   │   │   ├── doctor/DocumentViewer.tsx# Side-by-side OCR bounding box & fact viewer
│   │   │   ├── doctor/TimelineView.tsx# Longitudinal medical timeline
│   │   │   ├── doctor/ABDMHISModal.tsx# Simulated ABHA linking and HIS dispatch
│   │   │   └── doctor/FhirExportModal.tsx# HL7 FHIR R4 Bundle viewer & exporter
│   │   └── i18n/                      # Translations for English, Bengali, and Hindi
│   └── vite.config.ts                 # Vite bundler configuration & proxy settings
│
├── backend/                           # FastAPI Python Backend (Modular Monolith)
│   ├── app/
│   │   ├── main.py                    # Application entry point, middleware, CORS, routing
│   │   ├── api/
│   │   │   ├── deps.py                # Cookie extraction, JWT verification, role authorization
│   │   │   └── v1/                    # API endpoints:
│   │   │       ├── auth.py            # Phone OTP request, verify, dev sink, logout
│   │   │       ├── sessions.py        # Kiosk session creation & management
│   │   │       ├── interview.py       # Adaptive questionnaire progression
│   │   │       ├── speech.py          # Consent-gated audio transcription & TTS synthesis
│   │   │       ├── documents.py       # File upload, virus checks, OCR processing
│   │   │       ├── doctor.py          # Summary generation, edit, confirm, amendments
│   │   │       ├── medical.py         # Extracted medication & lab facts verification
│   │   │       └── triage.py          # Red-flag alert querying and WebSocket endpoint
│   │   ├── core/
│   │   │   ├── config.py              # Environment settings (Sarvam keys, DB URLs, flags)
│   │   │   ├── phone.py               # Indian phone number regex & E.164 normalization
│   │   │   └── errors.py              # Standardized API error envelopes
│   │   ├── models/                    # SQLAlchemy database models (Sessions, Facts, Audit, etc.)
│   │   ├── schemas/                   # Pydantic request/response validation contracts
│   │   │   └── fhir/                  # Internal FHIR R4 resource models (Composition, etc.)
│   │   ├── services/                  # Business logic & external adapters:
│   │   │   ├── auth_service.py        # OTP generation, SHA-256 hashing, session tokens
│   │   │   ├── interview_engine.py    # Adaptive decision-tree logic
│   │   │   ├── sarvam_speech.py       # Live Sarvam AI ASR & TTS client
│   │   │   ├── sarvam_ocr.py          # Live Sarvam Document Intelligence client
│   │   │   ├── red_flags.py           # Deterministic safety rule evaluator
│   │   │   ├── medical_facts.py       # Fact provenance & verification management
│   │   │   ├── clinical_summary.py    # SBAR summary drafting & immutable confirmation
│   │   │   ├── fhir.py                # NRCES-compliant HL7 FHIR R4 bundle builder
│   │   │   └── abdm.py                # Mock ABHA verification and Care Context linker
│   │   └── database.py                # SQLAlchemy engine & session maker
│   ├── alembic/versions/              # 12 versioned database migration scripts
│   └── tests/                         # 428 automated regression tests
│
├── ai/                                # AI Configuration, Prompts & Clinical Rule Sets
│   ├── complaint_flows/               # JSON decision trees (chest pain, fever, cough, etc.)
│   ├── safety_rules/red_flags_v1.json # Deterministic, versioned emergency screening rules
│   ├── ontology/concepts.json         # Approved whitelist of clinical concepts
│   └── document_fixtures/             # Sample synthetic prescriptions & lab reports
│
├── docs/                              # Project architecture, clinical scope & SIH guides
│   ├── sih-presentation-guide.md      # THIS PRESENTATION HANDBOOK
│   ├── architecture.md                # System architecture specification
│   ├── clinical-scope.md              # Clinical guidelines and boundaries
│   └── roadmap.md                     # Roadmap phases 1 through 12
│
└── scripts/                           # Developer automation scripts
    ├── start-backend-sqlite.ps1       # One-click backend launcher (SQLite + Sarvam)
    └── start-dev.ps1                  # Development launcher (PostgreSQL)
```

---

## 9. Feature Status Matrix: What is Working vs. What Remains

### 9.1 Fully Implemented & Verified Features (Working Now)

| Feature | Verified State | Proof & Test Evidence |
|---|---|---|
| **Phone OTP Authentication** | ✅ **Working & Verified** | Full phone OTP challenge/verify flow, rate limiting, dev sink, cookie management, tested via Playwright & pytest. |
| **Multilingual Kiosk UI** | ✅ **Working & Verified** | Complete UI dynamically renders in English, Bengali, and Hindi. |
| **Adaptive Interview Flow** | ✅ **Working & Verified** | 5 complaint flows + AYUSH flow dynamically adapt questions based on previous answers; preserves unanswered fields. |
| **Indian Speech AI (ASR & TTS)**| ✅ **Working & Verified** | Live Sarvam AI (`saarika:v2` ASR, `bulbul:v1` TTS) transcribes audio and reads questions; includes browser fallback. |
| **Voice Candidate Confirmation**| ✅ **Working & Verified** | Speech is NEVER saved directly without patient visual review, edit, and confirmation. |
| **Deterministic Red-Flag Alerts**| ✅ **Working & Verified** | Rule-based engine flags potential emergencies instantly; broadcasts to triage via WebSockets. |
| **Document Upload & OCR** | ✅ **Working & Verified** | Prescription and lab report OCR via Sarvam Document Intelligence extracts medications, doses, and lab flags. |
| **Fact Provenance Tracking** | ✅ **Working & Verified** | Extracted facts retain source document ID, bounding coordinates, confidence score, and `unverified` status. |
| **Longitudinal Timeline** | ✅ **Working & Verified** | Synthesizes current intake with past medical history into an interactive chronological timeline. |
| **Discrepancy Detection** | ✅ **Working & Verified** | Highlights clinical conflicts between patient self-reports and uploaded medical documents. |
| **Doctor Review & Verification** | ✅ **Working & Verified** | Doctor can verify/reject individual facts, view verbatim patient quotes, and inspect original documents. |
| **Clinical Summary Synthesis** | ✅ **Working & Verified** | Auto-generates structured draft summary; doctor can edit, regenerate, or addendum. |
| **Immutable Confirmation** | ✅ **Working & Verified** | Confirmed record is locked with cryptographic integrity, audit log, and timestamp. |
| **HL7 FHIR R4 Bundle Export** | ✅ **Working & Verified** | Generates validated NRCES/NDHM-compliant FHIR R4 bundles (`Composition`, `Patient`, `Observation`, etc.). |
| **ABDM / HIS Simulation** | ✅ **Working & Verified** | Mock ABHA number validation, Care Context Linking, and HIS dispatch receipt generation. |

---

### 9.2 In-Progress / Partial Features

| Feature | Current Reality | Next Step |
|---|---|---|
| **NVIDIA NIM Normalization** | Adapter implemented and schema-safe; live cloud API occasionally experiences network latency/timeouts. | Add a local cached semantic dictionary or deploy lightweight on-premise embeddings. |
| **Sarvam Translation** | Adapter exists and Bengali-to-English translation is verified; currently configured with mock provider for local demo speed. | Toggle `TRANSLATION_PROVIDER=sarvam` in `.env` for production deployments. |
| **BHASHINI Speech Adapter** | Complete code adapter and mock tests exist in backend. | Hook up live Government of India BHASHINI API credentials when sandbox access is granted. |

---

### 9.3 What Remains for Production Deployment (Roadmap to Hospital Go-Live)

1. **Production SMS Gateway:** Replace the mock/dev OTP provider with a commercial Indian SMS gateway (e.g., Gupshup, ValueFirst, Twilio India) with DLT template registration.
2. **Enterprise Hospital IAM:** Replace demo doctor login with hospital Active Directory / OAuth2 / OpenID Connect / Keycloak SSO with Multi-Factor Authentication (MFA).
3. **Official NHA ABDM Gateway Certification:** Move from mock ABHA verification to live National Health Authority (NHA) Sandbox M1, M2, and M3 milestone certification.
4. **Clinical Governance Review:** Formal clinical committee review of red-flag rules and symptom trees with medical college faculty.
5. **Encrypted Cloud Object Storage:** Store patient-uploaded medical documents in encrypted AWS S3 / Azure Blob storage with automated antivirus/antimalware scanning.
6. **DPDP Act 2023 Compliance:** End-to-end automated data anonymization, Right-to-be-Forgotten data purge pipelines, and verifiable audit logging.

---

## 10. Roadmap to Hospital Production Deployment

```text
Phase A (Current SIH Prototype)
  └─► Fully functioning local prototype, 5 complaint flows, Sarvam AI voice/OCR,
      deterministic safety rules, doctor review, FHIR export, SQLite/Postgres.

Phase B (Hospital Pilot / Sandbox - 3 Months)
  └─► Live SMS integration (DLT-registered), Keycloak doctor SSO,
      NHA ABDM Sandbox Milestone 1 & 2 integration, physical touch kiosk testing.

Phase C (Clinical Trial & Multi-Center Validation - 6 Months)
  └─► 500-patient pilot in district hospital OPD, measuring:
      (a) Consultation time saved, (b) Red-flag detection sensitivity,
      (c) Doctor acceptance rate, (d) Speech recognition accuracy across dialects.

Phase D (Full Production & State-Level Rollout - 12 Months)
  └─► Integration with state hospital HIS / e-Hospital systems,
      ABDM Milestone 3 full interoperability, edge-device offline capability.
```

---

## 11. Verification Evidence & Test Metrics

MediKiosk has undergone rigorous, multi-tiered software quality verification:

- **Backend Test Suite:** **428 automated pytest tests** passing (100% pass rate). Covering authentication security, token isolation, adaptive branching, red-flag triggers, document OCR, FHIR serialization, and audit logs.
- **Frontend Test Suite:** **104 Vitest + React Testing Library tests** passing. Covering language switching, touch stepper inputs, audio recorder states, and doctor verification modals.
- **End-to-End Regression Suite:** Headed **Playwright browser journeys** passing against real running servers (ports 5175 & 8010). Tests verified:
  - Phone OTP request -> Dev OTP retrieval -> Verified session cookie.
  - Full multilingual intake journey in Bengali.
  - Sarvam AI speech recording & transcript candidate confirmation.
  - Chest pain intake triggering red-flag priority alert.
  - Synthetic document upload and real-time OCR extraction.
  - Doctor workspace review, field-level verification, summary confirmation, and FHIR export.
  - Security boundary testing: Cross-patient data isolation and rejection of unauthenticated doctor access.

---

## 12. 6-to-8 Minute SIH Live Stage Demo Script

### Act 1: The Hook & The Problem (0:00 – 1:00)
> *"Respected judges, in high-volume Indian OPDs, a doctor has less than 3 minutes per patient. Over half that time is wasted breaking language barriers, typing demographic information, and deciphering crumpled paper records. Critical red-flag symptoms are easily missed.*  
> *We present **MediKiosk**—an AI-assisted, multilingual pre-consultation intake kiosk that structures patient history, digitizes past prescriptions, and checks for red flags BEFORE the patient meets the doctor."*

### Act 2: Patient Kiosk & Voice Intake (1:00 – 2:30)
> *(Open `http://127.0.0.1:5175/login` on screen)*  
> *"The patient enters their mobile number and receives an OTP. For today's demo, we click 'Auto-fill Test OTP' and log in.*  
> *The patient chooses their language—let's select **Bengali**. Notice how all UI elements and clinical questions immediately switch.*  
> *The kiosk offers granular consent: sharing with the doctor, audio processing, and document digitization.*  
> *Now, the patient reports their chief complaint: **Chest Pain**.*  
> *Instead of typing, the patient can speak naturally. MediKiosk connects to **Sarvam AI's speech models**, transcribing regional voice. Notice our core safety feature: **Transcript Confirmation**. The AI never directly commits speech to the medical record without the patient reviewing and confirming the text."*

### Act 3: Deterministic Red-Flag Safety Alert (2:30 – 3:30)
> *"As the patient indicates their chest pain is severe (9/10) and radiates to the left arm, watch what happens:*  
> *A high-priority emergency banner immediately appears. Simultaneously, on the nurse's **Triage Dashboard** (switch tab to `/triage`), a real-time WebSocket alert flashes!*  
> *Crucial architectural distinction: **This was NOT generated by a hallucinating LLM.** It was triggered by our deterministic, versioned safety rule engine. MediKiosk informs the patient that potential emergency symptoms are detected and flags them for immediate clinical assessment."*

### Act 4: Document Intelligence & OCR (3:30 – 4:30)
> *"Next, the patient uploads a picture of an old, crumpled prescription.*  
> *(Upload `prescription.png` from `ai/document_fixtures/`)*  
> *MediKiosk runs Sarvam Document Intelligence OCR. It extracts past medications (Metformin 500mg, Atorvastatin 10mg). But notice: every single extracted fact is tagged as **UNVERIFIED**. We never assume AI extractions are ground truth until a licensed clinician confirms them."*

### Act 5: Doctor Workspace & Longitudinal Timeline (4:30 – 6:00)
> *(Switch tab to Doctor Portal `http://127.0.0.1:5175/doctor`)*  
> *"Now, the doctor opens the patient's file. Look at what the doctor sees:*  
> *1. The patient's verbatim words in Bengali, with English translations.*  
> *2. A **Longitudinal Timeline** merging past medical records with today's intake.*  
> *3. **Discrepancy Detection:** The system flags that the patient reported no history of diabetes, yet their uploaded prescription clearly shows Metformin!*  
> *4. The doctor can view the original prescription image side-by-side with the OCR text and click **'Verify'** on each fact.*  
> *5. MediKiosk presents an auto-drafted clinical summary. The doctor can edit any text, and when satisfied, clicks **'Confirm Summary'**.*  
> *The record is now locked and cryptographically audited."*

### Act 6: Interoperability & Closing (6:00 – 7:00)
> *"Finally, we click **'Export FHIR'**. MediKiosk outputs a fully validated **HL7 FHIR R4 Bundle** adhering to India's NRCES and ABDM standards.*  
> *We simulate **ABHA Care Context Linking** and HIS integration.*  
> *In summary: MediKiosk doesn't replace the doctor. It empowers doctors with structured, verified, red-flag screened intelligence, turning a chaotic 3-minute intake into an effective, life-saving consultation. Thank you!"*

---

## 13. SIH Judge Q&A Defense Battlecard

#### Q1: "Are you using an LLM to diagnose patients? What about hallucinations and medical liability?"
> **Answer:** *"Absolutely not. MediKiosk has a strict, non-negotiable clinical boundary: **We never diagnose and we never prescribe.**  
> We do not use LLMs for clinical decisions or red-flag detection. Red flags are evaluated by a deterministic, rule-based Python engine against versioned JSON rules (`ai/safety_rules/red_flags_v1.json`).  
> Generative AI is strictly confined to natural language transcription (Sarvam ASR) and structured summary drafting. Every AI extraction is explicitly marked as 'unverified' until verified by the human clinician. The doctor remains 100% in control."*

#### Q2: "Why did you build a Modular Monolith instead of Microservices or Kubernetes?"
> **Answer:** *"This was an intentional architectural decision for Indian healthcare environments. A rural district hospital or community health center (CHC) does not have a DevOps team to manage Kubernetes clusters, Kafka brokers, and distributed network meshes.  
> Our modular monolith (FastAPI + React + PostgreSQL/SQLite) runs reliably on standard hospital hardware, can operate on local hospital LANs without internet dependency, has zero distributed-transaction failure modes, and can be containerized into a single Docker Compose deployment."*

#### Q3: "What happens if the internet goes down in a rural Primary Health Center (PHC)?"
> **Answer:** *"MediKiosk is designed with **graceful degradation**:  
> 1. **Network Offline:** The kiosk switches to touch-based intake with local question trees stored in browser cache and SQLite/PostgreSQL running on the local hospital server.  
> 2. **AI Provider Outage:** If cloud speech or OCR APIs are unreachable, the kiosk automatically falls back to browser-native Web Speech synthesis and queues document images locally for deferred processing.  
> Patient intake never halts because of cloud downtime."*

#### Q4: "How does your solution align with Government of India digital health initiatives (ABDM)?"
> **Answer:** *"MediKiosk is built from the ground up for the Ayushman Bharat Digital Mission (ABDM):  
> - It accepts and validates 14-digit ABHA numbers.  
> - Clinical data is exported in **HL7 FHIR R4 Bundles** adhering strictly to NRCES (National Resource Centre for EHR in India) profiles (`OPConsultRecord`).  
> - It supports ABDM Care Context Linking, enabling the patient's consultation brief to be pushed directly into their personal health record (PHR) app (like ABHA / Aarogya Setu)."*

#### Q5: "How do you handle patient data privacy under India’s DPDP Act 2023?"
> **Answer:** *"We enforce:  
> 1. **Granular Consent:** Independent opt-in toggles for doctor sharing, voice processing, and document OCR.  
> 2. **Data Minimization:** No raw audio is retained permanently; once transcribed and confirmed, audio buffers are purged.  
> 3. **Role-Based Access Control (RBAC):** Strict cryptographic cookie session bounds; patients can never access other patients' records or doctor portals.  
> 4. **Immutable Audit Trails:** Every field verification, summary edit, and document access is stamped with the actor ID and timestamp."*

#### Q6: "Why is SQLite being used in this local demo?"
> **Answer:** *"PostgreSQL is our primary production database, and full Alembic migrations are written and verified for PostgreSQL. In our current local Windows presentation environment, host-level Windows Application Control (WDAC) restricts the background PostgreSQL service executable. To guarantee 100% demo reliability without compromising host security policies, we enabled our robust, pre-built SQLite fallback (`.runtime/acceptance.sqlite`)."*

---

## 14. One-Slide Pitch Summary

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                                 MEDIKIOSK                                   │
│            AI-Assisted Pre-Consultation Clinical Intake & Triage            │
├─────────────────────────────────────────────────────────────────────────────┤
│  THE PROBLEM:                                                               │
│   • 3-minute OPD consultation crisis in Indian public hospitals.             │
│   • Severe language barriers, fragmented paper records, missed red flags.   │
│                                                                             │
│  OUR SOLUTION:                                                              │
│   • Multilingual Kiosk: Touch & Voice intake in English, Bengali, Hindi.     │
│   • Sarvam AI Speech: Regional Indian ASR with patient transcript review.   │
│   • Deterministic Red Flags: 100% explainable emergency safety screening.    │
│   • Document Intelligence: Prescription & lab report OCR with provenance.   │
│   • Longitudinal Timeline: Reconciles past documents with current symptoms. │
│   • Clinician Workspace: One-click field verification & draft summaries.    │
│   • ABDM / FHIR R4: Interoperable NRCES OPConsultRecord export.              │
│                                                                             │
│  CLINICAL SAFETY:                                                           │
│   • Never diagnoses. Never prescribes. Keeps human doctor firmly in control.│
│                                                                             │
│  CURRENT STATUS:                                                            │
│   • Phase 1–12 fully implemented; 428 backend + 104 frontend tests passing. │
└─────────────────────────────────────────────────────────────────────────────┘
```
