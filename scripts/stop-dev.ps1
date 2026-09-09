param([switch]$Database)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot '.runtime'
$processFile = Join-Path $runtimeRoot 'dev-processes.json'
if (Test-Path -LiteralPath $processFile) {
    $saved = Get-Content -Raw -LiteralPath $processFile | ConvertFrom-Json
    foreach ($property in $saved.PSObject.Properties) {
        $process = Get-CimInstance Win32_Process -Filter ("ProcessId = " + [int]$property.Value) -ErrorAction SilentlyContinue
        $expectedBackend = $property.Name -eq 'backend' -and $process.CommandLine -like ('*' + (Join-Path $projectRoot 'backend') + '*') -and $process.CommandLine -match 'uvicorn app.main:app'
        $expectedFrontend = $property.Name -eq 'frontend' -and $process.CommandLine -like ('*' + (Join-Path $projectRoot 'frontend') + '*') -and $process.CommandLine -match 'vite'
        if ($process -and ($expectedBackend -or $expectedFrontend)) { Stop-Process -Id $process.ProcessId }
    }
}
if ($Database) {
    & (Join-Path $runtimeRoot 'pgsql\bin\pg_ctl.exe') -D (Join-Path $runtimeRoot 'pgdata') -m fast -w stop
    if ($LASTEXITCODE -ne 0) { throw 'Could not stop the local PostgreSQL instance.' }
}
Write-Output 'Stopped the selected local development services. Data is retained.'
