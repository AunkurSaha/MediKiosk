param([string]$PythonPath)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runtimeRoot = Join-Path $projectRoot '.runtime'
$env:APP_ENV = 'demo'
$env:DEMO_MODE = 'true'
$env:CLINICAL_NORMALIZATION_PROVIDER = 'mock'
$env:SPEECH_PROVIDER = 'mock'
$env:TRANSLATION_PROVIDER = 'mock'
$env:OCR_PROVIDER = 'mock'
$env:RAG_EMBEDDING_PROVIDER = 'mock'
$env:RAG_GENERATION_PROVIDER = 'template'
$env:ABDM_ENV = 'mock'
$env:HIS_ENDPOINT_URL = ''

$python = if ($PythonPath) { $PythonPath } else { Join-Path $projectRoot 'backend\.venv\Scripts\python.exe' }
try { & $python --version *> $null; $pythonUsable = $LASTEXITCODE -eq 0 }
catch { $pythonUsable = $false }
if (-not $pythonUsable) {
    $python = Join-Path $env:USERPROFILE '.local\bin\python3.11.exe'
    $packages = Join-Path $runtimeRoot 'evidence-pydeps'
    if (-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath $packages)) {
        throw 'No usable local Python runtime was found.'
    }
    $env:PYTHONPATH = [string]::Join(';', @($packages, (Join-Path $projectRoot 'backend')))
}

Push-Location (Join-Path $projectRoot 'backend')
try {
    & $python -c "from app.database import engine; assert engine.url.get_backend_name() == 'postgresql'; assert engine.url.host and engine.url.host.endswith('.supabase.com'); print('Supabase PostgreSQL safety guard passed.')"
    if ($LASTEXITCODE -ne 0) { throw 'Supabase database safety guard failed.' }
    & $python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Supabase migration failed.' }
    & $python -m app.seed
    if ($LASTEXITCODE -ne 0) { throw 'Synthetic demo seed failed.' }
} finally {
    Pop-Location
}

Write-Output 'SUPABASE DEMO PREPARED'
Write-Output 'Only existing additive migrations and idempotent synthetic routing seed were applied.'
Write-Output 'No reset, truncate, drop, or patient deletion was performed.'
