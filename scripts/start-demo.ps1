param([switch]$Reset)

$ErrorActionPreference = 'Stop'
if ($Reset) {
    throw 'Supabase recording mode is non-destructive. Run scripts/prepare-supabase-demo.ps1 instead.'
}

# Recording mode deliberately uses the Supabase PostgreSQL URL from backend/.env.
# Keep automated browser isolation in start-e2e.ps1, which explicitly uses SQLite.
$env:APP_ENV = 'demo'
$env:DEMO_MODE = 'true'
$env:CLINICAL_NORMALIZATION_PROVIDER = 'mock'
$env:SPEECH_PROVIDER = 'mock'
$env:TRANSLATION_PROVIDER = 'mock'
$env:OCR_PROVIDER = 'mock'
$env:RAG_EMBEDDING_PROVIDER = 'mock'
$env:RAG_GENERATION_PROVIDER = 'template'
$env:ABDM_ENV = 'mock'
$env:HIS_ENDPOINT_URL = ''

$launcher = Join-Path $PSScriptRoot 'start-dev.ps1'
& $launcher -NormalizationProvider mock -SpeechProvider mock -OcrProvider mock -TranslationProvider mock
if ($LASTEXITCODE -ne 0) { throw 'MediKiosk Supabase demo startup failed.' }

Write-Output ''
Write-Output 'MediKiosk Demo Ready'
Write-Output 'Frontend: http://127.0.0.1:5175'
Write-Output 'Backend:  http://127.0.0.1:8010'
Write-Output 'Database: Supabase PostgreSQL (backend/.env)'
Write-Output 'Providers: deterministic local demo mode'
