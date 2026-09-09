$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot '.runtime'
New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
$archivePath = Join-Path $runtimeRoot 'postgresql-18.6.zip'
$binaryRoot = Join-Path $runtimeRoot 'pgsql'
if (-not (Test-Path -LiteralPath (Join-Path $binaryRoot 'bin\postgres.exe'))) {
    if (-not (Test-Path -LiteralPath $archivePath)) {
        Write-Output 'Downloading PostgreSQL 18.6 Windows binaries from EDB...'
        Invoke-WebRequest -UseBasicParsing -Uri 'https://sbp.enterprisedb.com/getfile.jsp?fileid=1260488' -OutFile $archivePath
    }
    Write-Output 'Extracting PostgreSQL...'
    Expand-Archive -LiteralPath $archivePath -DestinationPath $runtimeRoot -Force
}
& (Join-Path $binaryRoot 'bin\postgres.exe') --version
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL executable could not start.' }
$dataRoot = Join-Path $runtimeRoot 'pgdata'
$secretPath = Join-Path $runtimeRoot 'postgres-admin.txt'
if (-not (Test-Path -LiteralPath (Join-Path $dataRoot 'PG_VERSION'))) {
    if (Test-Path -LiteralPath $dataRoot) { throw 'Partial database directory exists; inspect it before retrying.' }
    $secretBytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($secretBytes)
    $rng.Dispose()
    $pgSecret = [Convert]::ToBase64String($secretBytes)
    [System.IO.File]::WriteAllText($secretPath, $pgSecret + [Environment]::NewLine)
    & (Join-Path $binaryRoot 'bin\initdb.exe') -D $dataRoot -U medikiosk_admin -E UTF8 --locale=C --auth=scram-sha-256 "--pwfile=$secretPath"
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL initialization failed.' }
    Add-Content -LiteralPath (Join-Path $dataRoot 'postgresql.conf') -Value @"
listen_addresses = '127.0.0.1'
port = 55432
"@
}
& (Join-Path $binaryRoot 'bin\pg_ctl.exe') -D $dataRoot status
if ($LASTEXITCODE -ne 0) {
    $pgStart = Start-Process -FilePath (Join-Path $binaryRoot 'bin\pg_ctl.exe') -ArgumentList @('-D', ('"' + $dataRoot + '"'), '-l', ('"' + (Join-Path $runtimeRoot 'postgres.log') + '"'), '-w', 'start') -WindowStyle Hidden -PassThru
    if (-not $pgStart.WaitForExit(60000)) { throw 'PostgreSQL start timed out.' }
    if ($pgStart.ExitCode -ne 0) { throw 'PostgreSQL failed to start; inspect .runtime/postgres.log.' }
}
& (Join-Path $projectRoot 'backend\.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'configure_database.py')
if ($LASTEXITCODE -ne 0) { throw 'Database provisioning failed.' }
Write-Output 'Local PostgreSQL is ready at 127.0.0.1:55432. Credentials are stored locally, not printed.'
