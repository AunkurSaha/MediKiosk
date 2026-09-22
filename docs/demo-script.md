# SIH demo script

## Primary story — document-aware patient (3–5 minutes)

### Step 0 — prepare

Run `powershell -ExecutionPolicy Bypass -File scripts/start-demo.ps1 -Reset`. Open `http://127.0.0.1:5175`. Use only fictional data.

Say: “This is an isolated local demonstration. No Supabase or external clinical system is used.”

### Step 1 — begin patient intake

Use Quick Demo Patient Login, choose Bengali or Hindi, enter fictional patient details, and grant doctor/document consent.

Say: “MediKiosk starts before the patient reaches the doctor, in a language and input mode they are comfortable with.”

### Step 2 — rapid routing

Choose fever without emergency answers. Confirm the `ROUTINE_OPD` result and General Medicine pathway, enter Kolkata, and select the recommended facility.

Say: “A small deterministic question set establishes the care route before the longer history. It does not diagnose.”

### Step 3 — doctor matching

Review eligible General Medicine doctors and select one.

Say: “Only active, accepting doctors with an eligible specialty and facility membership are shown.”

### Step 4 — document-aware intake

Upload `ai/document_fixtures/metformin_prescription.png` and `ai/document_fixtures/fasting_glucose_lab.png`. Confirm the medication when prompted, then complete the remaining interview.

Say: “Instead of asking the patient to repeat information already found in a document, MediKiosk asks a focused confirmation question. The laboratory result remains document-derived and unverified.”

Point out Clinical Coverage and the reduced question count. Do not interpret the laboratory value.

### Step 5 — queue handoff

Complete intake and show the persisted visit token and estimated wait. Refresh once to demonstrate recovery.

Say: “The visit is now assigned to the selected doctor. Queue position and waiting time are operational estimates, not appointments.”

### Step 6 — doctor workspace

Open a separate browser/profile, use Quick Demo Doctor Login for the selected facility/specialty, and open the patient. Show routing, history, coverage, medications, lab evidence, documents, queue token, and summary.

Open Evidence Attribution and expand “Why is this here?” for Metformin and the laboratory observation. Use “View source.”

Say: “MediKiosk does not just generate prose. Every important statement is traceable to the patient, a document, or a deterministic safety rule.”

## Secondary stories

### Routine fever — about 2 minutes

Hindi/Bengali → fever for three days → no red flags → Routine OPD → General Medicine → facility → doctor → interview → queue → summary.

### Cardiology matching — about 90 seconds

Non-emergency chest discomfort → Cardiology. Show one BUSY and one AVAILABLE cardiologist; confirm the dermatologist is absent. Select a cardiologist and complete intake.

### Emergency bypass — 30–45 seconds

Chest discomfort → severe/radiation emergency answers → emergency-capable facility → calm handoff. Show that normal doctor matching, adaptive continuation, and normal queue token are bypassed.

Say: “Potential emergency symptoms were detected. Immediate clinical assessment is recommended.”

### Conflict/provenance — about 90 seconds

Upload the prescription, answer “No” to current Metformin use, then open the doctor workspace. Show `CONFLICTED`, “Needs clarification,” both source values, and their provenance. Neither source is overwritten.

## Presenter timing

Primary story: 3–5 minutes. Emergency: 30–45 seconds. Keep Routine Fever and Cardiology as backups rather than presenting every scenario end-to-end.
