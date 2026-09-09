# UX / Product Design Specification — MediKiosk

## 1. Design goals

The patient experience should feel:
- simple;
- calm;
- readable;
- non-technical;
- language-friendly;
- usable with touch even when voice fails.

The doctor experience should feel:
- dense but scannable;
- evidence-oriented;
- editable;
- explicit about uncertainty.

The triage experience should feel:
- immediate;
- explainable;
- acknowledgement-oriented.

## 2. Patient kiosk principles

### One primary task per screen
Avoid large forms.

Good:
- “Choose your language.”
- “Do you agree to prepare a summary for your doctor?”
- “What problem brought you here today?”

Avoid:
- showing 20 medical-history fields at once.

### Large interactive targets
Buttons should be easily tappable on a kiosk/tablet.

### Persistent alternatives
When voice is offered, also make touch/type available.

### Repeat/confirm
For low-confidence speech:
- show “Did you say…?”
- allow confirm;
- allow retry;
- allow touch/type correction.

## 3. Patient route map

```text
/kiosk/language
→ /kiosk/identify
→ /kiosk/consent
→ /kiosk/interview
→ /kiosk/documents       # later phase
→ /kiosk/review          # later phase
→ /kiosk/complete
```

## 4. Language screen

Content:
- MediKiosk logo/name;
- welcome;
- language cards for English, বাংলা, हिन्दी.

Persist language in session/frontend state and preferably in backend session once created.

## 5. Identification screen

Prototype fields:
- patient name;
- hospital token;
- optional demo ABHA ID.

Actions:
- Continue.

Clearly label demo identity behavior. Do not imply real ABHA authentication if it is not connected.

## 6. Consent screen

Explain:
- answers will be processed;
- optional voice may be processed;
- documents may be processed;
- information will be shown to a doctor.

Provide separate toggles/checkboxes for:
- voice processing;
- document processing;
- sharing with doctor.

For prototype flow, sharing with doctor should be required to complete a clinical intake; if not granted, explain why the workflow cannot create a doctor-facing summary.

## 7. Interview screen

Primary layout:

```text
Progress / section
Question Header [ Listen / শুনুন / सुनें ] (QuestionAudioPlayer)
Optional short explanation
[ VoiceRecorder — Record answer ] (when voice consent is granted)
  ├── Recording pulse + timer + Done / Cancel
  ├── Uploading / Transcribing spinner
  └── Candidate Review Card: "You said: ..."
        ├── [ Confirm ] (persists source: 'voice')
        ├── [ Edit ]    (inline edit → persists source: 'typed')
        ├── [ Record again ]
        └── [ Cancel ]
[ typed / touch answer control ] (always available fallback)
Back / Continue when appropriate
```

Display the current question clearly.

### Text-to-Speech (TTS) Question Playback
- Localized button in the question header:
  - English: `🔊 Listen` / `🔊 Playing...`
  - Bengali: `🔊 শুনুন` / `🔊 বাজছে...`
  - Hindi: `🔊 सुनें` / `🔊 चल रहा है...`
- Synthesizes strictly the exact localized question text from the pinned complaint flow.
- User-triggered only; auto-play is strictly prohibited.
- If audio playback fails, displays a non-blocking retry button.

### Voice Input (ASR) & Candidate Review Card
- Microphone input is offered as an adjunct for open-ended spoken responses (`short_text` question types) when `voice_processing == true`.
- User explicitly clicks `Record answer` to start recording. MediaRecorder captures audio in browser memory.
- During recording, a visible pulsing red indicator and elapsed timer are shown with `Done` and `Cancel` controls.
- Upon stopping, audio is uploaded to `/interview/speech/transcribe` for ephemeral processing.
- The returned transcript is displayed prominently in a **Candidate Review Card**:
  - English: `You said:`
  - Bengali: `আপনি বলেছেন:`
  - Hindi: `आपने कहा:`
- The candidate transcript is **never** an interview answer automatically.
- Controls:
  - **Confirm**: Submits candidate text directly via the standard interview answer pathway with `source: "voice"`.
  - **Edit**: Transitions the candidate card into an editable text area. Upon saving, submits with `source: "typed"`.
  - **Record again**: Discards the current candidate and restarts recording.
  - **Cancel**: Dismisses candidate review card and returns to idle state.
- **Graceful Fallback**: If microphone permissions are denied, the browser lacks MediaRecorder, or transcription fails, a clear localized banner appears: `"Voice input is unavailable. Please type or select your answer."` The touch/type controls remain directly below and functional at all times.

Do not expose internal ontology IDs to patients.

## 8. Red-flag patient state

Do not display a diagnosis.

Use:

**“Potential emergency symptoms were detected. Medical staff should assess you promptly.”**

If the demo supports staff alert delivery:
**“Medical staff have been notified.”**

Only show the latter after backend acknowledgement that the alert was created/delivered to the alert system.

## 9. Triage dashboard

Route:
- `/triage`

Each alert card should show:
- priority;
- hospital token;
- patient/session reference;
- time;
- reason;
- triggering reported facts;
- status: new/acknowledged/resolved if implemented.

Example:

```text
URGENT
Token: OPD-104

Potential emergency symptoms detected
Reason:
✓ chest pain reported
✓ shortness of breath reported
✓ worse with exertion

[View intake] [Acknowledge]
```

## 10. Doctor dashboard

Routes:
- `/doctor`
- `/doctor/sessions/:sessionId`

Recommended page sections:

1. Patient/session header.
2. Current complaint/HPI.
3. Past history.
4. Medications/allergies.
5. Timeline.
6. Alerts.
7. Documents/extraction confidence.
8. Discrepancies.
9. Draft summary editor.
10. Confirm action.

## 11. Verification states

Use explicit labels:
- `Patient reported`
- `Document extracted`
- `Needs verification`
- `Doctor verified`
- `Low confidence`

Do not use a generic green check for AI-generated data unless a doctor/user has actually verified it.

## 12. Document display

When extraction is uncertain, let doctor view:
- original document;
- extracted text/fact;
- confidence;
- source date/page if available.

Never make uncertain OCR appear indistinguishable from confirmed data.

## 13. Summary editor

Show:
- generated/review draft;
- editable text or structured sections;
- confirmation button.

Before confirmation, label the content **Draft**.

After confirmation, show:
- confirmed by;
- confirmed at.

## 14. Accessibility

Minimum expectations:
- keyboard-accessible web UI;
- meaningful form labels;
- sufficient contrast;
- no color-only alert communication;
- readable font sizes;
- focus indicators;
- icon + text for important states;
- localized strings kept outside components.

## 15. Visual tone

Healthcare-like but not sterile:
- clean neutral surfaces;
- restrained accent color;
- red reserved for urgent alerts/errors;
- no excessive gradients/animations;
- avoid “AI magic” visuals that reduce credibility.

## 16. Loading/error UX

Never leave provider actions silent.

Examples:
- “Transcribing…”
- “Could not understand audio. Try again or type your answer.”
- “Document uploaded; extraction unavailable.”
- “Could not save your answer. Please retry.”

## 17. Kiosk completion

After completion:
- show session/token confirmation;
- clear patient-sensitive frontend state after a short controlled completion action;
- do not leave the previous patient’s data visible when starting a new intake.
