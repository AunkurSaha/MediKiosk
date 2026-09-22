$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run scripts/setup-ocr.ps1 first.' }

Push-Location $root
try {
    Write-Output 'Starting local OCR at http://127.0.0.1:8020'
    & $python -m uvicorn app.main:app --host 127.0.0.1 --port 8020
} finally {
    Pop-Location
}
