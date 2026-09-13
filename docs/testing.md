# Testing

Run tests with explicit mock providers unless a live-provider evaluation is intended.
Mock tests verify adapter behavior only; they do not establish live service reliability.

## Backend

From `backend/`:

```powershell
.\.venv\Scripts\ruff.exe check app tests
.\.venv\Scripts\python.exe -m pytest -q
```

The backend test configuration is in `backend/pyproject.toml`. Tests use fixtures from
`backend/tests/conftest.py`; do not point automated tests at patient or demonstration data.

## Frontend

From `frontend/`:

```powershell
npm run lint
npm run format:check
npm test
npm run build
```

For browser coverage, start the local stack and run:

```powershell
npm run test:e2e
```

The Playwright suite uses synthetic records. Live-provider journeys use the separate
`playwright.live.config.ts` configuration and must never be reported as passing unless the
external provider was actually contacted successfully.

## Database and restart checks

From the repository root:

```powershell
backend\.venv\Scripts\python.exe scripts\verify-stabilization-migrations.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-stabilization-restart.ps1 -ApplicationOnly
```

The migration verifier uses disposable schemas and checks upgrade continuity plus Alembic/model
alignment. Application-only restart verification does not prove PostgreSQL process restart.

## Security checks

Run the focused security verifier from the repository root:

```powershell
backend\.venv\Scripts\python.exe scripts\verify-stabilization-security.py
```

Clinical, authentication, provenance, and immutable-review behavior must remain covered by the
automated suites. See [requirements traceability](requirements-traceability.md) for the mapping
between requirements and acceptance evidence.
