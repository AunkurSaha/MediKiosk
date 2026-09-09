param([switch]$Postgres)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $projectRoot 'backend')
try {
    if ($Postgres) {
        & .\.venv\Scripts\python.exe ..\scripts\test_postgres.py
    } else {
        & .\.venv\Scripts\python.exe -m pytest -q
    }
    if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed.' }
    & .\.venv\Scripts\ruff.exe check app tests alembic
    if ($LASTEXITCODE -ne 0) { throw 'Backend lint failed.' }
} finally { Pop-Location }

