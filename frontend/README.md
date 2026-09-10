# MediKiosk frontend

React, Vite, TypeScript, and Tailwind. The current Phase 12 prototype includes patient intake, staff triage, doctor evidence/summary review, FHIR preview, mock ABDM/HIS controls, and synthetic showcase tools.

From this directory:

```powershell
npm ci
npm run dev
npm run lint
npm run format:check
npm test
npm run build
```

Development URL: http://127.0.0.1:5175. Requests to `/api` are proxied to http://127.0.0.1:8010. Start the backend/database first using the root `scripts/start-dev.ps1` launcher.

For the actual browser acceptance tests:

```powershell
npx playwright install chromium
npm run test:e2e
```

These use a fresh headless browser and synthetic data against the running local app. They do not use your signed-in browser. See [setup](../docs/setup.md) and [implementation status](../docs/implementation-status.md).
