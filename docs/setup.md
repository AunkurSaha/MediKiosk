# Local development setup

## Configured machine

The current local configuration uses Python 3.14, PostgreSQL 18.6, and the Node/npm installation already on this machine. Python dependencies are constrained in `backend/requirements.lock`; frontend versions are in `frontend/package-lock.json`.

Start from `C:\MEDIKIOSK`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-dev.ps1
```

The app is at http://127.0.0.1:5175 and the API docs at http://127.0.0.1:8010/docs. The launcher binds both servers to loopback and creates hidden processes. It does not stop unrelated services on the older ports.

## Fresh installation on Windows

Install Python (3.14 tested) and Node.js (22.12+ or a compatible newer release). Then, from the project root:

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt
cd frontend
npm ci
cd ..
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup-postgres.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-dev.ps1
```

Use your Python executable's full path if `python` is not on PATH. The older `backend/venv` remains untouched; use `backend/.venv` for this implementation.

The database setup downloads PostgreSQL 18.6 Windows binaries through [EDB](https://www.enterprisedb.com/download-postgresql-binaries), the binary provider linked by [PostgreSQL's Windows download page](https://www.postgresql.org/download/windows/). It initializes a project-local cluster, listens only on 127.0.0.1:55432, uses SCRAM passwords, and creates:

- `medikiosk`: local app database;
- `medikiosk_test`: separate acceptance-test database;
- `medikiosk` app role: owns those databases; not a cluster superuser.

Random credentials are saved locally and not printed. The admin password is in `.runtime/postgres-admin.txt`; the app connection string is in `backend/.env`. These files must remain ignored. No Windows service, system PATH entry, or public listener is installed.

The setup is repeatable after success. If interrupted partway through initial provisioning, it stops rather than deleting or overwriting an existing database/role. Inspect the reported partial state before retrying.

## Existing PostgreSQL or another operating system

Create a dedicated application database and role, copy `backend/.env.example` to `backend/.env`, and set `DATABASE_URL` to a `postgresql+psycopg://...` URL. Do not use the portable Windows launcher with a separately managed database. Run the backend/frontend manually:

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

Application runtime and migrations use the same configuration. SQLite is permitted only with `APP_ENV=test`. The previous SQLite files have not been migrated or deleted; only newly created synthetic intakes are in PostgreSQL.

## Configuration

- `DATABASE_URL`: backend-only PostgreSQL connection string.
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
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/stop-dev.ps1 -Database
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-dev.ps1
```

Stop commands retain all data. App process IDs are recorded in `.runtime/dev-processes.json` and verified before stopping them. PostgreSQL does not start automatically after Windows restarts; run the launcher.

Logs are under `.runtime/`. If a launcher reports a port conflict, inspect the logs and existing process before stopping anything. Do not delete database folders as a troubleshooting shortcut.
