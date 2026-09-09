param([ValidateSet('mock', 'nvidia', 'disabled')][string]$NormalizationProvider)

$ErrorActionPreference = 'Stop'
if ($NormalizationProvider) {
    # Explicit process override; preserves the user's backend/.env and credentials.
    $env:CLINICAL_NORMALIZATION_PROVIDER = $NormalizationProvider
    $env:CLINICAL_NORMALIZATION_TIMEOUT_SECONDS = if ($NormalizationProvider -eq 'nvidia') { '8' } else { '0.5' }
}
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot '.runtime'
& (Join-Path $PSScriptRoot 'setup-postgres.ps1')
$pythonPath = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
Push-Location (Join-Path $projectRoot 'backend')
try {
    & $pythonPath -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
    & $pythonPath -m app.seed
    if ($LASTEXITCODE -ne 0) { throw 'Demo doctor seeding failed.' }
} finally { Pop-Location }
$processes = @{}
if (Test-Path -LiteralPath (Join-Path $runtimeRoot 'dev-processes.json')) {
    $previous = Get-Content -Raw -LiteralPath (Join-Path $runtimeRoot 'dev-processes.json') | ConvertFrom-Json
    foreach ($property in $previous.PSObject.Properties) { $processes[$property.Name] = $property.Value }
}
function Test-HttpReady([string]$url) {
    try { return (Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 2).StatusCode -eq 200 }
    catch { return $false }
}
if (-not (Test-HttpReady 'http://127.0.0.1:8010/api/health')) {
    $backendProcess = Start-Process -FilePath $pythonPath -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--app-dir', ('"' + (Join-Path $projectRoot 'backend') + '"'), '--host', '127.0.0.1', '--port', '8010') -WorkingDirectory (Join-Path $projectRoot 'backend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeRoot 'backend.out.log') -RedirectStandardError (Join-Path $runtimeRoot 'backend.err.log')
    $processes['backend'] = $backendProcess.Id
}
if (-not (Test-HttpReady 'http://127.0.0.1:5175')) {
    $nodePath = (Get-Command node.exe).Source
    $vitePath = Join-Path $projectRoot 'frontend\node_modules\vite\bin\vite.js'
    $frontendProcess = Start-Process -FilePath $nodePath -ArgumentList @(('"' + $vitePath + '"'), '--host', '127.0.0.1', '--port', '5175', '--strictPort') -WorkingDirectory (Join-Path $projectRoot 'frontend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeRoot 'frontend.out.log') -RedirectStandardError (Join-Path $runtimeRoot 'frontend.err.log')
    $processes['frontend'] = $frontendProcess.Id
}
$processes | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeRoot 'dev-processes.json')
$ready = $false
for ($attempt = 0; $attempt -lt 15; $attempt++) {
    if ((Test-HttpReady 'http://127.0.0.1:8010/api/health') -and (Test-HttpReady 'http://127.0.0.1:5175')) { $ready = $true; break }
    Start-Sleep -Seconds 1
}
if (-not $ready) { throw 'A service did not become ready. Inspect .runtime/*.err.log for errors or a port conflict.' }
foreach ($service in @(@{Name='backend'; Port=8010; Marker='backend'}, @{Name='frontend'; Port=5175; Marker='frontend'})) {
    $listener = Get-NetTCPConnection -LocalPort $service.Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) {
        $running = Get-CimInstance Win32_Process -Filter ("ProcessId = " + $listener.OwningProcess)
        if ($running.CommandLine -like ('*' + (Join-Path $projectRoot $service.Marker) + '*')) {
            $processes[$service.Name] = $running.ProcessId
        }
    }
}
$processes | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeRoot 'dev-processes.json')
Write-Output 'MediKiosk: http://127.0.0.1:5175'
Write-Output 'API docs: http://127.0.0.1:8010/docs'
