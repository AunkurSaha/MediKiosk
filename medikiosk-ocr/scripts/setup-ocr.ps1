$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    $uv = (Get-Command uv.exe -ErrorAction Stop).Source
    $env:UV_CACHE_DIR = Join-Path $root '.uv-cache'
    & $uv venv (Join-Path $root '.venv') --python 3.11 --seed
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python 3.11 OCR environment.' }
}

$version = & $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($version -ne '3.11') { throw "Expected Python 3.11, found $version" }

& $python -c "import cv2, mlflow, tensorflow" 2>$null
if ($LASTEXITCODE -ne 0) {
    & $python -m pip install -r (Join-Path $root 'requirements-medikiosk.txt')
    if ($LASTEXITCODE -ne 0) { throw 'OCR dependency installation failed.' }
}

& $python -m pip check
if ($LASTEXITCODE -ne 0) { throw 'OCR environment has incompatible dependencies.' }
& $python -c "import cv2, mlflow, tensorflow; print('OCR imports ready')"

Write-Output "OCR environment ready: $python"
