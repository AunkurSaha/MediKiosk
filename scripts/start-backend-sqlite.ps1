# start-backend-sqlite.ps1
# Starts the MediKiosk backend using the local SQLite acceptance database.
# Use when PostgreSQL is unavailable (e.g., blocked by Application Control).
# The SQLite file at backend/runtime/acceptance.sqlite must already be migrated to head.
# Keeping it under backend/runtime makes the path agree with backend/.env even
# when the launcher is invoked from the repository root.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\start-backend-sqlite.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\start-backend-sqlite.ps1 -SpeechProvider sarvam
#
# SECURITY: This script never prints SARVAM_API_KEY, SMS credentials,
# session tokens, or OTPs. Set SMS_PROVIDER=mock (the default) for local dev.

param(
    [ValidateSet('mock', 'nvidia', 'disabled')][string]$NormalizationProvider,
    [ValidateSet('mock', 'bhashini', 'sarvam', 'disabled')][string]$SpeechProvider,
    [ValidateSet('mock', 'sarvam', 'disabled')][string]$OcrProvider,
    [ValidateSet('mock', 'sarvam', 'disabled')][string]$TranslationProvider
)

$ErrorActionPreference = 'Stop'
$projectRoot   = Split-Path -Parent $PSScriptRoot
$runtimeRoot   = Join-Path $projectRoot '.runtime'
$sqlitePath    = Join-Path $projectRoot 'backend\runtime\acceptance.sqlite'
$pythonPath    = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
$backendDir    = Join-Path $projectRoot 'backend'

if (-not (Test-Path -LiteralPath $sqlitePath)) {
    throw "Acceptance database not found at $sqlitePath. Run migrations first."
}

# Override provider env vars if specified
if ($NormalizationProvider) { $env:CLINICAL_NORMALIZATION_PROVIDER = $NormalizationProvider }
if ($SpeechProvider)         { $env:SPEECH_PROVIDER = $SpeechProvider }
if ($OcrProvider)            { $env:OCR_PROVIDER = $OcrProvider }
if ($TranslationProvider)    { $env:TRANSLATION_PROVIDER = $TranslationProvider }

# Required for SQLite: APP_ENV must be "test" to pass the database.py guard.
$env:APP_ENV       = 'test'
$env:DATABASE_URL  = "sqlite:///$($sqlitePath.Replace('\', '/'))"
$env:DEMO_MODE     = 'true'
# SMS_PROVIDER defaults to mock; do not set to a real provider here.
if (-not $env:SMS_PROVIDER) { $env:SMS_PROVIDER = 'mock' }

Write-Output "Backend database : SQLite (acceptance.sqlite)"
Write-Output "DEMO_MODE        : $($env:DEMO_MODE)"
Write-Output "SMS_PROVIDER     : $($env:SMS_PROVIDER)"
Write-Output "APP_ENV          : $($env:APP_ENV)"

# Run Alembic upgrade to ensure the SQLite file is at head
Push-Location $backendDir
try {
    & $pythonPath -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'SQLite migration failed.' }
    & $pythonPath -m app.seed
    if ($LASTEXITCODE -ne 0) { throw 'Demo doctor seeding failed.' }
} finally { Pop-Location }

# Kill any previous MediKiosk backend on port 8010
$listener = Get-NetTCPConnection -LocalPort 8010 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    $running = Get-CimInstance Win32_Process -Filter ("ProcessId = " + $listener.OwningProcess) -ErrorAction SilentlyContinue
    if ($running -and $running.CommandLine -match 'uvicorn app.main:app') {
        Write-Output "Stopping previous backend (PID $($running.ProcessId))..."
        Stop-Process -Id $running.ProcessId -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 500
    }
}

# Write a temporary .cmd launcher so environment variables are correctly set in
# the new process. PowerShell 5.1's Start-Process -WindowStyle Hidden spawns a
# new session and does NOT inherit in-process $env: assignments; passing them
# through a cmd script is the reliable cross-version approach.
$smsProvider   = $env:SMS_PROVIDER
$sarvamApiKey  = $env:SARVAM_API_KEY   # may be empty; cmd will pass through
$normProv      = $env:CLINICAL_NORMALIZATION_PROVIDER
$speechProv    = $env:SPEECH_PROVIDER
$ocrProv       = $env:OCR_PROVIDER
$transProv     = $env:TRANSLATION_PROVIDER
$sqliteUrl     = "sqlite:///$($sqlitePath.Replace('\', '/'))"
$launcherPath  = Join-Path $runtimeRoot 'start-backend.cmd'
$cmdLines = @(
    '@echo off'
    "set APP_ENV=test"
    "set DATABASE_URL=$sqliteUrl"
    "set DEMO_MODE=true"
    "set SMS_PROVIDER=$smsProvider"
)
if ($sarvamApiKey)  { $cmdLines += "set SARVAM_API_KEY=$sarvamApiKey" }
if ($normProv)      { $cmdLines += "set CLINICAL_NORMALIZATION_PROVIDER=$normProv" }
if ($speechProv)    { $cmdLines += "set SPEECH_PROVIDER=$speechProv" }
if ($ocrProv)       { $cmdLines += "set OCR_PROVIDER=$ocrProv" }
if ($transProv)     { $cmdLines += "set TRANSLATION_PROVIDER=$transProv" }
$cmdLines += "`"$pythonPath`" -m uvicorn app.main:app --app-dir `"$backendDir`" --host 127.0.0.1 --port 8010"
$cmdLines | Set-Content -LiteralPath $launcherPath -Encoding ASCII

# Start backend via cmd launcher
Write-Output "Starting backend on http://127.0.0.1:8010 ..."
$backendProcess = Start-Process `
    -FilePath 'cmd.exe' `
    -ArgumentList @('/C', "`"$launcherPath`"") `
    -WorkingDirectory $backendDir `
    -WindowStyle Hidden `
    -PassThru `
    -RedirectStandardOutput (Join-Path $runtimeRoot 'backend.out.log') `
    -RedirectStandardError  (Join-Path $runtimeRoot 'backend.err.log')

# Save PID
$processFile = Join-Path $runtimeRoot 'dev-processes.json'
$processes = @{}
if (Test-Path -LiteralPath $processFile) {
    $saved = Get-Content -Raw -LiteralPath $processFile | ConvertFrom-Json
    foreach ($prop in $saved.PSObject.Properties) { $processes[$prop.Name] = $prop.Value }
}
$processes['backend'] = $backendProcess.Id
$processes | ConvertTo-Json | Set-Content -LiteralPath $processFile

# Wait for health check
$ready = $false
for ($i = 0; $i -lt 20; $i++) {
    try {
        $resp = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8010/api/health' -TimeoutSec 2
        if ($resp.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
    Start-Sleep -Milliseconds 500
}

if (-not $ready) {
    Write-Output "--- backend.err.log (last 30 lines) ---"
    Get-Content -Tail 30 (Join-Path $runtimeRoot 'backend.err.log') -ErrorAction SilentlyContinue
    throw "Backend did not become healthy. Inspect .runtime/backend.err.log."
}

# Start-Process tracks the cmd launcher, while the listening Uvicorn worker is
# its Python child. Record the actual listener so stop-dev.ps1 can reliably
# stop the backend after later source changes.
$listener = Get-NetTCPConnection -LocalPort 8010 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
if (-not $listener) { throw 'Backend is healthy but no listener was found on port 8010.' }
$running = Get-CimInstance Win32_Process -Filter ("ProcessId = " + $listener.OwningProcess)
if (-not $running -or $running.CommandLine -notlike ('*' + $backendDir + '*')) {
    throw 'Port 8010 is not owned by the expected MediKiosk backend.'
}
$processes['backend'] = $running.ProcessId
$processes | ConvertTo-Json | Set-Content -LiteralPath $processFile

Write-Output "Backend healthy  : http://127.0.0.1:8010/api/health"
Write-Output "API docs         : http://127.0.0.1:8010/docs"
Write-Output "MediKiosk UI     : http://127.0.0.1:5175"
Write-Output "Backend PID      : $($running.ProcessId)"
