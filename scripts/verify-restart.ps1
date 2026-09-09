$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot '.runtime'
$sample = Get-Content -Raw -LiteralPath (Join-Path $runtimeRoot 'last-e2e.json') | ConvertFrom-Json
$uri = 'http://127.0.0.1:8010/api/doctor/sessions/' + $sample.sessionId
$headers = @{'X-Demo-Doctor' = 'true'}
$before = Invoke-RestMethod -Uri $uri -Headers $headers
if ($before.summary.status -ne 'confirmed') { throw 'Run the browser test first; its synthetic record must be confirmed.' }
$oldProcesses = Get-Content -Raw -LiteralPath (Join-Path $runtimeRoot 'dev-processes.json') | ConvertFrom-Json
$oldPgPid = Get-Content -LiteralPath (Join-Path $runtimeRoot 'pgdata\postmaster.pid') -TotalCount 1
$normalizationChecks = @()
foreach ($entry in @(@{File='last-phase3a-e2e.json'; Doctor=$true}, @{File='phase3a-resume.json'; Doctor=$false}, @{File='last-phase3b-e2e.json'; Doctor=$true}, @{File='phase3b-resume.json'; Doctor=$false})) {
    $referencePath = Join-Path $runtimeRoot $entry.File
    if (Test-Path -LiteralPath $referencePath) {
        $reference = Get-Content -Raw -LiteralPath $referencePath | ConvertFrom-Json
        $checkUri = if ($entry.Doctor) { 'http://127.0.0.1:8010/api/doctor/sessions/' + $reference.sessionId } else { 'http://127.0.0.1:8010/api/sessions/' + $reference.sessionId + '/interview' }
        $snapshot = Invoke-RestMethod -Uri $checkUri -Headers $headers
        $normalizationChecks += @{Uri=$checkUri; Before=($snapshot | ConvertTo-Json -Depth 60 -Compress); Name=$entry.File}
    }
}
$phase2Path = Join-Path $runtimeRoot 'last-phase2-e2e.json'
$resumePath = Join-Path $runtimeRoot 'phase2-resume.json'
$phase2Before = $null
$resumeBefore = $null
if (Test-Path -LiteralPath $phase2Path) {
    $phase2 = Get-Content -Raw -LiteralPath $phase2Path | ConvertFrom-Json
    $phase2Uri = 'http://127.0.0.1:8010/api/doctor/sessions/' + $phase2.sessionId
    $phase2Before = Invoke-RestMethod -Uri $phase2Uri -Headers $headers
    if ($phase2Before.summary.status -ne 'confirmed') { throw 'Phase 2 browser record must be confirmed.' }
}
if (Test-Path -LiteralPath $resumePath) {
    $resume = Get-Content -Raw -LiteralPath $resumePath | ConvertFrom-Json
    $resumeUri = 'http://127.0.0.1:8010/api/sessions/' + $resume.sessionId + '/interview'
    $resumeBefore = Invoke-RestMethod -Uri $resumeUri
    if ($resumeBefore.question.question_id -ne $resume.questionId) { throw 'Unexpected saved interview cursor.' }
}
& (Join-Path $PSScriptRoot 'stop-dev.ps1') -Database
$stillResponding = $false
try { $null = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8010/api/health' -TimeoutSec 2; $stillResponding = $true } catch {}
if ($stillResponding) { throw 'Backend did not stop; restart evidence would be invalid.' }
& (Join-Path $PSScriptRoot 'start-dev.ps1')
$after = Invoke-RestMethod -Uri $uri -Headers $headers
$newProcesses = Get-Content -Raw -LiteralPath (Join-Path $runtimeRoot 'dev-processes.json') | ConvertFrom-Json
$newPgPid = Get-Content -LiteralPath (Join-Path $runtimeRoot 'pgdata\postmaster.pid') -TotalCount 1
if ($oldProcesses.backend -eq $newProcesses.backend -or $oldPgPid -eq $newPgPid) { throw 'Expected new backend and database processes after restart.' }
if ($after.summary.reviewed_text -ne $sample.reviewed -or $after.summary.status -ne 'confirmed') { throw 'Confirmed record did not survive restart.' }
if ($before.summary.confirmed_at -ne $after.summary.confirmed_at -or $before.summary.generated_text -ne $after.summary.generated_text) { throw 'Confirmation timestamp or original draft changed.' }
if (($before.answers | ConvertTo-Json -Depth 10 -Compress) -ne ($after.answers | ConvertTo-Json -Depth 10 -Compress)) { throw 'Patient answers changed across restart.' }
Write-Output 'PASS: new backend and PostgreSQL processes; patient answers, draft, reviewed text and confirmation metadata survived restart.'
foreach ($check in $normalizationChecks) {
    $snapshot = Invoke-RestMethod -Uri $check.Uri -Headers $headers
    if ($check.Before -ne ($snapshot | ConvertTo-Json -Depth 60 -Compress)) { throw ('Normalization changed across restart: ' + $check.Name) }
    Write-Output ('PASS: source, normalization/provenance and session state survived restart: ' + $check.Name)
}
if ($phase2Before) {
    $phase2After = Invoke-RestMethod -Uri $phase2Uri -Headers $headers
    if (($phase2Before | ConvertTo-Json -Depth 50 -Compress) -ne ($phase2After | ConvertTo-Json -Depth 50 -Compress)) { throw 'Phase 2 confirmed record changed across restart.' }
    Write-Output 'PASS: Phase 2 active structured history, source provenance, draft and confirmed review survived restart.'
}
if ($resumeBefore) {
    $resumeAfter = Invoke-RestMethod -Uri $resumeUri
    if (($resumeBefore | ConvertTo-Json -Depth 50 -Compress) -ne ($resumeAfter | ConvertTo-Json -Depth 50 -Compress)) { throw 'Adaptive interview state changed across restart.' }
    Write-Output 'PASS: in-progress adaptive interview retained flow snapshot, cursor, revision, answers and language across restart.'
}
