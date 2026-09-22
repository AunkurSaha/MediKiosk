$ErrorActionPreference = 'Stop'
$ocrRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $ocrRoot '.venv\Scripts\python.exe'
$logDir = Join-Path $ocrRoot 'outputs\generalization-continuation'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$trainingArguments = @(
    'scripts\train_generalization.py', '--epochs', '10', '--batch-size', '32',
    '--start-epoch', '11', '--resume-weights', 'models\generalization_flor.weights.h5',
    '--checkpoint', 'models\generalization_continued_flor.weights.h5',
    '--early-stopping-patience', '5', '--early-stopping-min-delta', '0.002'
)
$trainingProcess = Start-Process -FilePath $pythonPath -ArgumentList $trainingArguments `
    -WorkingDirectory $ocrRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $logDir 'stdout.log') `
    -RedirectStandardError (Join-Path $logDir 'stderr.log')
Write-Output "Training PID: $($trainingProcess.Id)"
Write-Output "Logs: $logDir"
