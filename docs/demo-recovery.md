# Demo recovery

All recovery paths assume the isolated local E2E database and fictional data.

| Failure | Fastest recovery |
|---|---|
| Sarvam unavailable | Continue with touch/text. Demo mode uses mock speech and translation providers. |
| NVIDIA unavailable | Continue normally. Demo mode uses deterministic normalization and template RAG wording. |
| OCR unavailable | Use the versioned fixture images with `OCR_PROVIDER=mock`. If upload still fails, continue by typing the medication and state that document processing is temporarily unavailable. |
| Microphone denied | Close the permission prompt and use the visible text/touch control. Voice is optional. |
| Browser refreshes | Reopen the same route. The authenticated user and session ID are retained; routing, selection, interview answers, and queue entry are server-persisted. |
| Backend restarts | Run `scripts/start-demo.ps1` without `-Reset`; the existing `.runtime/e2e.sqlite` is reused. Refresh the browser after health returns. |
| Document upload fails | Retry once with `ai/document_fixtures/metformin_prescription.png`. Continue with text entry if it fails again; do not claim that extraction occurred. |
| Frontend becomes blank | Open `http://127.0.0.1:5175/kiosk/language`. If health checks fail, stop local processes and restart without reset. |
| Demo data becomes inconsistent | Stop local demo processes, then run `scripts/start-demo.ps1 -Reset`. This recreates only `.runtime/e2e.sqlite`. |
| Queue estimate unavailable | The visit token remains persisted. Explain that the estimate is temporarily unavailable and continue to the doctor workspace. |

Logs are in `.runtime/e2e-backend.err.log` and `.runtime/e2e-frontend.err.log`. Never switch the demo to a remote database as a recovery shortcut.
