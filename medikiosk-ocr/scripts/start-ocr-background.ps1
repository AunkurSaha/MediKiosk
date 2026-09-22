$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$output = Join-Path $root 'outputs'
New-Item -ItemType Directory -Force -Path $output | Out-Null

$listener = Get-NetTCPConnection -LocalPort 8020 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    throw 'Port 8020 is already in use. The script will not stop an unrelated process.'
}

$process = Start-Process -FilePath $python `
    -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8020') `
    -WorkingDirectory $root `
    -WindowStyle Hidden `
    -PassThru `
    -RedirectStandardOutput (Join-Path $output 'service.out.log') `
    -RedirectStandardError (Join-Path $output 'service.err.log')

Write-Output "OCR process started: $($process.Id)"
