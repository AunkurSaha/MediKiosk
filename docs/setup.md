# Local development setup

## Configured machine

The current configuration uses Python 3.14, a Supabase PostgreSQL project, and the Node/npm installation already on this machine. Python dependencies are constrained in `backend/requirements.lock`; frontend versions are in `frontend/package-lock.json`.

Start from `C:\MEDIKIOSK`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-dev.ps1 -SkipSeed
```

The app is at http://127.0.0.1:5175 and the API docs at http://127.0.0.1:8010/docs. The launcher binds both servers to loopback and creates hidden processes. It does not stop unrelated services on the older ports.

`-SkipSeed` keeps routine server availability independent of the optional bulk demo fixture setup:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-dev.ps1 -SkipSeed
```

## Fresh installation on Windows

Install Python (3.14 tested) and Node.js (22.12+ or a compatible newer release). Then, from the project root:

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt
cd frontend
npm ci
cd ..
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-dev.ps1 -SkipSeed
```

Use your Python executable's full path if `python` is not on PATH. The older `backend/venv` remains untouched; use `backend/.venv` for this implementation.

Copy `backend/.env.example` to `backend/.env`, then paste the backend-only Session pooler URL from the Supabase Connect dialog. Run the backend/frontend manually with:

```powershell
cd backend
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m app.seed
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

In a second terminal:

```powershell
cd frontend
npm run dev
```

On Linux/macOS, use `.venv/bin/python` instead of the Windows executable path.

Application runtime and migrations use the same Supabase configuration. Runtime startup rejects local PostgreSQL and SQLite URLs. SQLite is retained only for isolated automated tests.

## Configuration

- `DATABASE_URL`: backend-only Supabase PostgreSQL connection string with `sslmode=require`.
- `APP_ENV=development`: local development.
- `DEMO_MODE=true`: enables explicitly labeled demo-doctor access after seeding.
- `CORS_ORIGINS`: comma-separated permitted frontend origins, defaulting to local port 5175.
- `CLINICAL_NORMALIZATION_PROVIDER`: `mock`, `disabled`, or `nvidia`; the optional launcher switch overrides it for that process only.
- `SPEECH_PROVIDER`: `mock`, `disabled`, `sarvam`, or `bhashini`. Sarvam uses the backend-only `SARVAM_API_KEY`; optional pinned model, speaker, and bounded timeout settings are listed in `backend/.env.example`. BHASHINI remains separately configurable.
- `OCR_PROVIDER`: `mock` or `disabled`; real OCR is not implemented.
- `ABDM_ENV`, `ABDM_CLIENT_ID`, `ABDM_CLIENT_SECRET`, `HIS_ENDPOINT_URL`: reserved integration configuration; the shipped demonstration remains mock/simulated.
- `VITE_API_BASE_URL`: optional frontend variable, default `/api`; never put backend credentials in it.

The frontend development server proxies `/api` to port 8010. Credentials remain backend-only. The launcher uses `backend/.env` unless an explicit process override is supplied and restarts a project-owned backend when its active normalization provider is stale. `APP_ENV=production` disables demo doctor access; production authentication is separate future work.

## Stop and restart

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/stop-dev.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-dev.ps1 -SkipSeed
```

Stop commands retain all Supabase data. App process IDs are recorded in `.runtime/dev-processes.json` and verified before stopping them.

Logs are under `.runtime/`. If a launcher reports a port conflict, inspect the logs and existing process before stopping anything. Do not delete database folders as a troubleshooting shortcut.
