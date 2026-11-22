# Gap-closure tests: T17 fault injection, T25 request tampering via pause hook.
$ErrorActionPreference = 'Continue'
$repo = 'D:\AI\ASES-DeepSeek'
$adapter = Join-Path $repo 'enforcement\adapters\ases-agent'
$wrapper = Join-Path $adapter 'wrapper.ps1'

# ---------- isolated root ----------
$testRoot = Join-Path $env:TEMP ("ases-agent-gap-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path (Join-Path $testRoot 'run'), (Join-Path $testRoot 'state\ops'), (Join-Path $testRoot 'config'), (Join-Path $testRoot 'logs') | Out-Null
[System.IO.File]::WriteAllText((Join-Path $testRoot '.ases-agent-test-root'), 'sentinel', (New-Object System.Text.UTF8Encoding($false)))
Copy-Item -LiteralPath (Join-Path $adapter 'config\policy.json') -Destination (Join-Path $testRoot 'config\policy.json') -Force

# ---------- T17 cleanup-failure injection ----------
$env:ASES_AGENT_ROOT = $testRoot
$env:ASES_TEST_PAT = 'fake-gap-pat'
$env:ASES_TEST_CLEANUP_FAIL = '1'
$r = & powershell -NoProfile -ExecutionPolicy Bypass -File $wrapper 'whoami' '{}' 2>&1 | Out-String
$code = $LASTEXITCODE
Remove-Item Env:\ASES_TEST_CLEANUP_FAIL -ErrorAction SilentlyContinue
$blockerCreated = Test-Path -LiteralPath (Join-Path $testRoot 'state\cleanup_failed')
Write-Output ("T17_INJECT exit=$code cleanup_failure=$($r -match 'CLEANUP_FAILURE') blocker_created=$blockerCreated")

# subsequent op must be rejected
$r2 = & powershell -NoProfile -ExecutionPolicy Bypass -File $wrapper 'whoami' '{}' 2>&1 | Out-String
$code2 = $LASTEXITCODE
Write-Output ("T17_REJECT exit=$code2 rejected=$($r2 -match 'CLEANUP_FAILURE')")
Remove-Item -LiteralPath (Join-Path $testRoot 'state\cleanup_failed') -Force -ErrorAction SilentlyContinue
Remove-Item Env:\ASES_AGENT_ROOT, Env:\ASES_TEST_PAT -ErrorAction SilentlyContinue

# ---------- T25 request tampering via pause hook ----------
$env:ASES_AGENT_ROOT = $testRoot
$env:ASES_TEST_PAT = 'fake-gap-pat'
$env:ASES_TEST_PAUSE_AFTER_REQUEST = '1'
$wproc = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File', $wrapper, 'whoami', '{}') -PassThru -WindowStyle Hidden
$marker = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 500
    $m = Get-ChildItem -LiteralPath (Join-Path $testRoot 'run') -Filter '*.pause-after-request' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($m) { $marker = $m; break }
}
if ($marker) {
    $opId = $marker.BaseName -replace '\.pause-after-request$', ''
    $reqPath = Join-Path $testRoot "run\$opId.request.json"
    $tampered = (Get-Content -LiteralPath $reqPath -Raw).Replace('"params":', '"extra_key":"x","params":')
    [System.IO.File]::WriteAllText($reqPath, $tampered, (New-Object System.Text.UTF8Encoding($false)))
    Remove-Item -LiteralPath $marker.FullName -Force
} else {
    Write-Output "T25_TAMPER marker_not_found"
}
$wproc.WaitForExit(30000) | Out-Null
$ledger = Get-ChildItem -LiteralPath (Join-Path $testRoot 'state\ops') -Filter '*.json' -ErrorAction SilentlyContinue | ForEach-Object { Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json } | Select-Object -Last 1
Write-Output ("T25_TAMPER wrapper_exit=$($wproc.ExitCode) ledger_state=$($ledger.state) ledger_note=$($ledger.note)")
Remove-Item Env:\ASES_AGENT_ROOT, Env:\ASES_TEST_PAT, Env:\ASES_TEST_PAUSE_AFTER_REQUEST -ErrorAction SilentlyContinue

Write-Output "GAP_CLOSURE_DONE"
