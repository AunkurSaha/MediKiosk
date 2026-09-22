# SIH demo checklist

## Before judges arrive

- [ ] Stop any process already using ports 8010 or 5175.
- [ ] Run `scripts/start-demo.ps1 -Reset`.
- [ ] Confirm the terminal prints `DATABASE: local SQLite`, `REMOTE DATABASE CHANGES: DISABLED`, and `MediKiosk Demo Ready`.
- [ ] Verify backend health returns 200 at `http://127.0.0.1:8010/api/health`.
- [ ] Verify the frontend loads at `http://127.0.0.1:5175`.
- [ ] Verify Quick Demo Patient Login, Doctor Login, and Triage Login.
- [ ] Verify `metformin_prescription.png` and `fasting_glucose_lab.png` upload using mock OCR.
- [ ] Verify General Medicine and Cardiology directory data.
- [ ] Verify one cardiologist is AVAILABLE, one is BUSY, and Dermatology is excluded from Cardiology matching.
- [ ] Run the emergency scenario and verify normal matching/queue bypass.
- [ ] Verify the doctor summary opens and “Why is this here?” expands.
- [ ] Verify the triage alert shows rule ID, triggering information, status, and acknowledgment.
- [ ] Treat microphone input as optional; verify touch/text works.
- [ ] Set browser zoom to 100% and use a readable window size.
- [ ] Disable notifications and close unrelated tabs/terminals.
- [ ] Keep fixture files and a backup recording locally available.

## Immediately before presenting

- [ ] Patient browser/profile is logged in and on the welcome screen.
- [ ] Doctor browser/profile is logged in to the planned facility.
- [ ] Triage browser/profile is ready for the emergency backup story.
- [ ] No real patient information is visible.
- [ ] Primary story timer target is 3–5 minutes.
