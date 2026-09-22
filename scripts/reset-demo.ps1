param()

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runtimeRoot = Join-Path $projectRoot '.runtime'
$databasePath = Join-Path $runtimeRoot 'e2e.sqlite'
$expectedPath = [System.IO.Path]::GetFullPath((Join-Path $projectRoot '.runtime\e2e.sqlite'))
$resolvedTarget = [System.IO.Path]::GetFullPath($databasePath)
$processFile = Join-Path $runtimeRoot 'e2e-processes.json'

Write-Output 'MEDIKIOSK DEMO RESET'
Write-Output 'DATABASE: LOCAL E2E SQLITE'
Write-Output 'REMOTE DATABASE: DISABLED'

if ($resolvedTarget -ne $expectedPath) {
    throw "Unsafe demo database target: $resolvedTarget"
}
if ($env:DATABASE_URL -and $env:DATABASE_URL -notlike 'sqlite:*') {
    Write-Output 'Ignoring inherited remote DATABASE_URL; it will not be contacted.'
}

New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
if (Test-Path -LiteralPath $processFile) {
    $saved = Get-Content -Raw -LiteralPath $processFile | ConvertFrom-Json
    foreach ($property in $saved.PSObject.Properties) {
        if ($property.Name -in @('backend', 'frontend')) {
            $processId = [int]$property.Value
            if (Get-Process -Id $processId -ErrorAction SilentlyContinue) {
                Stop-Process -Id $processId -Force
                Wait-Process -Id $processId -ErrorAction SilentlyContinue
            }
        }
    }
    Remove-Item -LiteralPath $processFile -Force
}
$env:APP_ENV = 'e2e'
$env:DATABASE_URL = 'sqlite:///' + ($databasePath.Replace('\', '/'))
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

Push-Location (Join-Path $projectRoot 'backend')
try {
    Write-Output "DATABASE_URL = $env:DATABASE_URL"
    Write-Output "Running SQLite safety guard..."
    & $pythonPath -c "from app.database import engine; assert engine.url.drivername == \`"sqlite\`"; engine.dispose(); print(engine.url)"
    if ($LASTEXITCODE -ne 0) { throw 'Local SQLite safety guard failed.' }
    if (Test-Path -LiteralPath $databasePath) {
        $maxAttempts = 5
        for ($i = 0; $i -lt $maxAttempts; $i++) {
            try {
                if (Test-Path -LiteralPath $databasePath) {
                    Remove-Item -LiteralPath $databasePath -Force
                    break
                }
            } catch {
                if ($i -eq ($maxAttempts - 1)) { throw }
                Start-Sleep -Milliseconds 200
            }
        }
    }
    & $pythonPath -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Local demo migration failed.' }
    & $pythonPath -m app.e2e_seed
    if ($LASTEXITCODE -ne 0) { throw 'Local demo seed failed.' }
} finally {
    Pop-Location
}

Write-Output "RESET COMPLETE: $databasePath"
Write-Output 'Only the dedicated local E2E database was recreated.'
