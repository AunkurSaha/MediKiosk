# SIH Golden Video Demo Checklist

## Before recording

This recording path uses **Supabase PostgreSQL** for both the patient and doctor. Do not use
`start-e2e.ps1` for the recording; that launcher intentionally uses isolated SQLite.

1. Run `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/prepare-supabase-demo.ps1`.
   This applies only repository migrations and an idempotent synthetic facility/doctor seed. It
   does not reset, truncate, or delete Supabase data.
2. Run `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-demo.ps1`.
3. Confirm `http://127.0.0.1:8010/api/health` and `http://127.0.0.1:5175/` return HTTP 200.
4. Open the patient flow at `http://127.0.0.1:5175/login` in the recording browser.
5. Open a separate browser/profile for the doctor and sign in with:
   - identifier: `9876500012`
   - password: `Doctor@123`
   - hospital: MediKiosk Central Hospital
   - specialty: General Medicine
6. Keep both locked recording files ready in the file picker:
   - `ai/document_fixtures/recording_prescription.png`
   - `ai/document_fixtures/recording_lab_report.jpg`
   Recording mode uses deterministic extraction for these exact supplied bytes. Renaming is safe;
   modifying, screenshotting, recompressing, or re-exporting either file is not.
7. Set both browsers to 100% zoom, close DevTools, and disable notifications.

## Patient recording

1. Click **Continue as patient**.
2. Choose **English**.
3. Choose **Planning my visit**.
4. Review the prefilled synthetic identity, then click **Continue**.
   MediKiosk creates an internal intake reference automatically; do not enter a hospital token.
5. Grant share-with-doctor and document-processing consent; leave voice optional.
6. Click **Start intake**.
7. At **What brings you here today?**, choose **Fever**.
8. Enter `38` °C and answer **No** to breathing difficulty.
9. Click **Find a suitable facility**.
10. Enter locality `Kolkata`, then click **Search by locality**.
11. Select the first recommended facility.
12. Select **Dr. Ishan Gupta — General Medicine — Available**.
13. Upload `ai/document_fixtures/recording_prescription.png`.
14. Pause on **Information found in your prescription** and show the patient context plus the six
    visible entries: ORS Powder, Racecadotril 100 mg TDS, Azithromycin 500 mg OD, Ondansetron 4 mg
    SOS, Paracetamol 650 mg SOS, and Probiotic Capsule BD.
15. Enter `Fever since yesterday; no breathing difficulty.` for the main concern.
16. At each document confirmation, answer accurately for the recording case. Show that confirmed
    document medication evidence covers the generic medication-history branch.
17. Answer the remaining focused history questions. Generic duplicate medication questions must not
    appear after the confirmed document evidence.
18. Review and finish the intake.
19. Pause on **Your pre-consultation intake is ready** to show facility, doctor, visit token, and approximate waiting time.
20. Click **Show QR** and show the secure handoff QR plus its authorized-staff instruction.

## Doctor recording

1. In the prepared doctor profile, open `/doctor` and refresh once if it was opened before patient completion.
2. Open **Demo Patient**.
3. Show the chief complaint/current history, queue state, clinical coverage, and prescription document.
4. In **Medical facts**, show **Racecadotril**, **100 mg**, and **TDS**, then briefly show the other
   prescription facts as unverified until clinician review.
5. In **Clinical Summary**, open **Evidence Attribution**.
6. Find the Racecadotril statement and click **Why is this here?**.
7. Show the chain from uploaded prescription extraction to patient confirmation.
8. Return to **Summary Editor** and briefly show the readable structured clinical summary.

## Recovery

- Upload/extraction fails: confirm document consent is checked and `/api/config` reports
  `"ocr_provider":"mock"`, then retry the exact repository file. The deterministic provider accepts
  registered fixture bytes only; do not edit, screenshot, recompress, or substitute either file.
- Stale patient session: log out and click **Continue as patient** again. Supabase recording mode does
  not delete prior patient sessions.
- Queue is not clean: use a new synthetic demo-patient journey. Do not run `reset-demo.ps1` against
  the Supabase recording workflow; that script is retained only for local SQLite E2E recovery.
- Doctor cannot see the patient: confirm Dr. Ishan Gupta, Central Hospital, and General Medicine were used; refresh `/doctor` after intake completion.
- Packet already revoked or QR is stale: reset and replay the patient journey. Each **Show QR** action rotates the opaque handoff token.
- Browser auth is stale: log out in that browser/profile and sign in again. Keep patient and doctor sessions in separate profiles.
- A live provider appears slow: stop recording and restart in demo mode. The recording path must report deterministic local mock/sandbox providers, never production-live integrations.

## Emergency Q&A Demo

Use this separate synthetic case only if a judge asks about emergency symptoms; do not replace the main fever recording.

1. Use a new synthetic demo-patient journey. Do not reset Supabase.
2. At `/login`, click **Continue as patient**, choose **English**, accept the prefilled identity, grant share-with-doctor consent, and click **Start intake**.
3. Choose **Chest discomfort**. Enter severity `9`, answer **No** to current breathlessness, then **Yes** to discomfort spreading to the arm, jaw, back, or another area.
4. Show **Potential emergency symptoms detected**, **Immediate clinical assessment recommended**, and **How was this detected?**
5. Point out the recorded clinical safety alert and that routine doctor matching and the normal queue pathway are paused. The offered facility action is emergency-capable care, not the routine ranking path.

The trigger is the existing deterministic severe-radiating-chest-pain rule. It is not an AI diagnosis.

## Joint-pain backup path

Use this short second scenario when demonstrating breadth: choose **Joint pain**, complete the
quick safety check, then show the Orthopedics facility/doctor recommendation. The focused history
asks about the affected joint, onset, injury, swelling/redness/warmth, movement, morning stiffness,
fever, recurrence, and current pain medicine. It remains a patient-reported intake, not a diagnosis.
