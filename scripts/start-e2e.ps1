param([switch]$Reset)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runtimeRoot = Join-Path $projectRoot '.runtime'
$databasePath = Join-Path $runtimeRoot 'e2e.sqlite'
New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null

function Test-Ready([string]$url) {
    try { return (Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 2).StatusCode -eq 200 }
    catch { return $false }
}
if (Test-Ready 'http://127.0.0.1:8010/api/health') {
    throw 'Port 8010 is already serving an app; stop it before starting local E2E mode.'
}
if (Test-Ready 'http://127.0.0.1:5175') {
    throw 'Port 5175 is already serving an app; stop it before starting local E2E mode.'
}

# Explicit overrides take precedence over backend/.env. Never inherit its remote URL.
$env:APP_ENV = 'e2e'
$env:DATABASE_URL = 'sqlite:///' + ($databasePath -replace '\\', '/')
$env:DEMO_MODE = 'true'
$env:CLINICAL_NORMALIZATION_PROVIDER = 'mock'
$env:SPEECH_PROVIDER = 'mock'
$env:TRANSLATION_PROVIDER = 'mock'
$env:OCR_PROVIDER = 'mock'
$env:RAG_EMBEDDING_PROVIDER = 'mock'
$env:RAG_GENERATION_PROVIDER = 'template'
$env:ABDM_ENV = 'mock'
$env:HIS_ENDPOINT_URL = ''
$env:STORAGE_LOCAL_DIR = Join-Path $runtimeRoot 'e2e-uploads'

$pythonPath = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
try { & $pythonPath --version *> $null; $pythonUsable = $LASTEXITCODE -eq 0 }
catch { $pythonUsable = $false }
if (-not $pythonUsable) {
    $pythonPath = Join-Path $env:USERPROFILE '.local\bin\python3.11.exe'
    $packages = Join-Path $runtimeRoot 'evidence-pydeps'
    if (-not (Test-Path -LiteralPath $pythonPath) -or -not (Test-Path -LiteralPath $packages)) {
        throw 'No usable local Python runtime was found.'
    }
    $env:PYTHONPATH = [string]::Join(';', @($packages, (Join-Path $projectRoot 'backend')))
}

# The database module independently rejects any E2E URL other than this exact file.
Push-Location (Join-Path $projectRoot 'backend')
try {
    & $pythonPath -c 'from app.database import engine; print(engine.url)'
    if ($LASTEXITCODE -ne 0) { throw 'Local E2E database guard failed.' }
    if ($Reset) {
        if ((Resolve-Path -LiteralPath $runtimeRoot).Path -ne (Split-Path -Parent $databasePath)) {
            throw 'Unsafe E2E database path.'
        }
        if (Test-Path -LiteralPath $databasePath) { Remove-Item -LiteralPath $databasePath -Force }
    }
    & $pythonPath -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Local SQLite migration failed.' }
    & $pythonPath -m app.e2e_seed
    if ($LASTEXITCODE -ne 0) { throw 'Local E2E seed failed.' }
} finally { Pop-Location }

$backendDir = Join-Path $projectRoot 'backend'
$frontendDir = Join-Path $projectRoot 'frontend'
$backendProcess = Start-Process -FilePath $pythonPath -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--app-dir', ('"' + $backendDir + '"'), '--host', '127.0.0.1', '--port', '8010') -WorkingDirectory $backendDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeRoot 'e2e-backend.out.log') -RedirectStandardError (Join-Path $runtimeRoot 'e2e-backend.err.log')
$nodePath = (Get-Command node.exe).Source
$vitePath = Join-Path $frontendDir 'node_modules\vite\bin\vite.js'
$frontendProcess = Start-Process -FilePath $nodePath -ArgumentList @(('"' + $vitePath + '"'), '--host', '127.0.0.1', '--port', '5175', '--strictPort') -WorkingDirectory $frontendDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeRoot 'e2e-frontend.out.log') -RedirectStandardError (Join-Path $runtimeRoot 'e2e-frontend.err.log')
@{ backend = $backendProcess.Id; frontend = $frontendProcess.Id } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeRoot 'e2e-processes.json')
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    if ((Test-Ready 'http://127.0.0.1:8010/api/health') -and (Test-Ready 'http://127.0.0.1:5175')) { break }
    Start-Sleep -Seconds 1
}
if (-not (Test-Ready 'http://127.0.0.1:8010/api/health') -or -not (Test-Ready 'http://127.0.0.1:5175')) {
    throw 'Local E2E services did not become ready; inspect .runtime/e2e-*.err.log.'
}
Write-Output 'MEDIKIOSK LOCAL E2E MODE'
Write-Output "DATABASE: local SQLite ($databasePath)"
Write-Output 'REMOTE DATABASE CHANGES: DISABLED'
Write-Output 'Backend: http://127.0.0.1:8010/api/health (200)'
Write-Output 'Frontend: http://127.0.0.1:5175 (200)'
Write-Output 'MediKiosk Demo Ready'
