$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run scripts/setup-ocr.ps1 first.' }

Push-Location $root
try {
    if (-not (Test-Path -LiteralPath (Join-Path $root 'datasets\synthetic\tiny\manifest.csv'))) {
        & $python scripts\build_tiny_dataset.py
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    & $python -m pip check
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $python -m pytest -q tests
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $python -c "from app.recognizer import FlorLineRecognizer, ROOT; r=FlorLineRecognizer(ROOT/'models'/'tiny_flor.weights.h5'); print({'recognizer_loaded': True, 'device': 'cpu', 'model': r.model_version})"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}
