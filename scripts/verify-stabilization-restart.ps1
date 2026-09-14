$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot '.runtime'
$headers = @{'X-Demo-Doctor' = 'true'}
$checks = @()
foreach ($entry in @(
    @{File='last-e2e.json'; Kind='doctor'},
    @{File='last-phase2-e2e.json'; Kind='doctor'},
    @{File='phase2-resume.json'; Kind='interview'},
    @{File='last-phase3a-e2e.json'; Kind='doctor'},
    @{File='phase3a-resume.json'; Kind='interview'},
    @{File='stabilization-alert-reference.json'; Kind='doctor'},
    @{File='stabilization-document-reference.json'; Kind='doctor'},
    @{File='phase7-reference.json'; Kind='facts'},
    @{File='phase7-reference.json'; Kind='timeline'},
    @{File='phase7-reference.json'; Kind='discrepancies'}
)) {
    $path = Join-Path $runtimeRoot $entry.File
    if (-not (Test-Path -LiteralPath $path)) { throw ('Missing browser evidence: ' + $entry.File) }
    $reference = Get-Content -Raw -LiteralPath $path | ConvertFrom-Json
    $uri = switch ($entry.Kind) {
        'doctor' { 'http://127.0.0.1:8010/api/doctor/sessions/' + $reference.sessionId }
        'interview' { 'http://127.0.0.1:8010/api/sessions/' + $reference.sessionId + '/interview' }
        'facts' { 'http://127.0.0.1:8010/api/doctor/sessions/' + $reference.sessionId + '/medical-facts' }
        'timeline' { 'http://127.0.0.1:8010/api/doctor/sessions/' + $reference.sessionId + '/timeline' }
        'discrepancies' { 'http://127.0.0.1:8010/api/doctor/sessions/' + $reference.sessionId + '/discrepancies' }
    }
    $before = Invoke-RestMethod -Uri $uri -Headers $headers
    $checks += @{Name=$entry.File; SessionId=$reference.sessionId; Uri=$uri; Before=($before | ConvertTo-Json -Depth 80 -Compress)}
    if ($reference.documentId) {
        $fileUri = 'http://127.0.0.1:8010/api/sessions/' + $reference.sessionId + '/documents/' + $reference.documentId + '/file'
        $fileBefore = Join-Path $runtimeRoot 'restart-document-before.png'
        Invoke-WebRequest -UseBasicParsing -Uri $fileUri -Headers $headers -OutFile $fileBefore
        $fileHash = (Get-FileHash -LiteralPath $fileBefore -Algorithm SHA256).Hash
    }
}
$processPath = Join-Path $runtimeRoot 'dev-processes.json'
$oldProcesses = Get-Content -Raw -LiteralPath $processPath | ConvertFrom-Json
& (Join-Path $PSScriptRoot 'stop-dev.ps1')
$responding = $false
try { $null = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8010/api/health' -TimeoutSec 2; $responding = $true } catch {}
if ($responding) { throw 'Backend did not stop; restart evidence is invalid.' }
& (Join-Path $PSScriptRoot 'start-dev.ps1') -NormalizationProvider mock -SkipSeed
$newProcesses = Get-Content -Raw -LiteralPath $processPath | ConvertFrom-Json
if ($oldProcesses.backend -eq $newProcesses.backend -or $oldProcesses.frontend -eq $newProcesses.frontend) { throw 'Application process IDs did not change.' }
foreach ($check in $checks) {
    $after = Invoke-RestMethod -Uri $check.Uri -Headers $headers
    if ($check.Before -ne ($after | ConvertTo-Json -Depth 80 -Compress)) { throw ('Persisted API state changed: ' + $check.Name) }
}
$fileAfter = Join-Path $runtimeRoot 'restart-document-after.png'
Invoke-WebRequest -UseBasicParsing -Uri $fileUri -Headers $headers -OutFile $fileAfter
if ((Get-FileHash -LiteralPath $fileAfter -Algorithm SHA256).Hash -ne $fileHash) { throw 'Stored document bytes changed.' }
$mode = 'application-only-supabase'
@{mode=$mode; passed=$true; records=@($checks | ForEach-Object { @{reference=$_.Name; session_id=$_.SessionId; api_state_unchanged=$true} }); document_sha256=$fileHash; backend_pid_changed=$true; frontend_pid_changed=$true; timestamp=(Get-Date).ToString('o')} |
    ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $runtimeRoot ('stabilization-restart-' + $mode + '.json')) -Encoding UTF8
Write-Output ('PASS: ' + $mode + ' restart; ' + $checks.Count + ' persisted API snapshots and original document bytes unchanged.')
