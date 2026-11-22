# Final local security verification: direct-runner matrix, result tampering, strict-validation vectors.
$ErrorActionPreference = 'Continue'
$adapter = 'D:\AI\ASES-DeepSeek\enforcement\adapters\ases-agent'
$wrapper = Join-Path $adapter 'wrapper.ps1'
$runner = Join-Path $adapter 'runner.ps1'
$prod = "$env:USERPROFILE\.ases-agent"

function New-TestRoot {
    $tr = Join-Path $env:TEMP ("ases-verify-" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path (Join-Path $tr 'run'), (Join-Path $tr 'state\ops'), (Join-Path $tr 'config'), (Join-Path $tr 'logs') | Out-Null
    [System.IO.File]::WriteAllText((Join-Path $tr '.ases-agent-test-root'), 's', (New-Object System.Text.UTF8Encoding($false)))
    Copy-Item (Join-Path $adapter 'config\policy.json') (Join-Path $tr 'config\policy.json') -Force
    return $tr
}
function New-Request([string]$tr, [string]$opId, [string]$raw) {
    [System.IO.File]::WriteAllText((Join-Path $tr "run\$opId.request.json"), $raw, (New-Object System.Text.UTF8Encoding($false)))
}
function Run-RunnerDirect([string]$tr, [string]$opId, [string]$rr) {
    $out = & powershell -NoProfile -ExecutionPolicy Bypass -File $runner -OpId $opId -TestPat fake -UseMockGh -RuntimeRoot $rr 2>&1 | Out-String
    return @{ code=$LASTEXITCODE; out=$out }
}

# ===== 1. Direct-runner matrix =====
$tr = New-TestRoot
# 1a: ASES_AGENT_ROOT set, no -RuntimeRoot -> test root
$opId = [guid]::NewGuid().ToString()
New-Request $tr $opId '{"schema":"ases-agent-op-request/1","op_id":"' + $opId + '","op":"whoami","params":{},"created_utc":"' + (Get-Date).ToUniversalTime().ToString('o') + '","expires_utc":"' + (Get-Date).ToUniversalTime().AddMinutes(10).ToString('o') + '","policy_sha256":"x"}'
$env:ASES_AGENT_ROOT = $tr
$r = & powershell -NoProfile -ExecutionPolicy Bypass -File $runner -OpId $opId -TestPat fake -UseMockGh 2>&1 | Out-String
Write-Output ("RUNNER_1a_override_no_root exit=$LASTEXITCODE result_in_test_root=$(Test-Path "$tr\run\$opId.result.json")")
Remove-Item Env:\ASES_AGENT_ROOT -ErrorAction SilentlyContinue

# 1b: ASES_AGENT_ROOT set + -RuntimeRoot=production -> reject
$env:ASES_AGENT_ROOT = $tr
$r = Run-RunnerDirect $tr ([guid]::NewGuid().ToString()) $prod
Write-Output ("RUNNER_1b_override_prod exit=$($r.code) rejected=$($r.out -match 'cannot target the production runtime')")
Remove-Item Env:\ASES_AGENT_ROOT -ErrorAction SilentlyContinue

# 1c/1d: production-mode (wrapper-launched) runner — NOT TESTED (would touch production); code-inspection only
Write-Output "RUNNER_1c_production_mode NOT_TESTED (production target forbidden; code-inspection: -RuntimeRoot=production with no override returns production)"

# 1e: invalid root (missing sentinel) -> reject
$tr2 = New-TestRoot
Remove-Item -LiteralPath (Join-Path $tr2 '.ases-agent-test-root') -Force
$r = Run-RunnerDirect $tr2 ([guid]::NewGuid().ToString()) $tr2
Write-Output ("RUNNER_1e_missing_sentinel exit=$($r.code) rejected=$($r.out -match 'sentinel')")

# 1e2: non-existent root -> reject
$r = Run-RunnerDirect $tr2 ([guid]::NewGuid().ToString()) "$env:TEMP\does-not-exist-xyz"
Write-Output ("RUNNER_1e2_missing_path exit=$($r.code) rejected=$($r.out -match 'does not exist')")

# ===== 2. Result tampering (pause-before-result) =====
$tr3 = New-TestRoot
$env:ASES_AGENT_ROOT = $tr3
$env:ASES_TEST_PAT = 'fake-verify-pat'
$env:ASES_TEST_PAUSE_BEFORE_RESULT_VALIDATE = '1'
$wp = Start-Process powershell.exe -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File', $wrapper, 'whoami', '{}') -PassThru -WindowStyle Hidden
$marker = $null
for ($i=0; $i -lt 60; $i++) {
    Start-Sleep -Milliseconds 500
    $m = Get-ChildItem (Join-Path $tr3 'run') -Filter '*.pause-before-result' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($m) { $marker = $m; break }
}
if ($marker) {
    $opId = $marker.BaseName -replace '\.pause-before-result$', ''
    $rp = Join-Path $tr3 "run\$opId.result.json"
    $before = Get-Content $rp -Raw
    $after = $before -replace '"login":"chautinhtinh3979"', '"login":"evil-tampered"'
    [System.IO.File]::WriteAllText($rp, $after, (New-Object System.Text.UTF8Encoding($false)))
    Write-Output ("T25_RESULT_TAMPER login_modified=$($after -ne $before)")
    Remove-Item $marker.FullName -Force
} else { Write-Output "T25_RESULT_TAMPER marker_not_found" }
$wp.WaitForExit(30000) | Out-Null
$led = Get-ChildItem (Join-Path $tr3 'state\ops') -Filter '*.json' -ErrorAction SilentlyContinue | ForEach-Object { Get-Content $_.FullName -Raw | ConvertFrom-Json } | Select-Object -Last 1
Write-Output ("T25_RESULT_TAMPER wrapper_exit=$($wp.ExitCode) ledger_state=$($led.state) ledger_note=$($led.note)")
Remove-Item Env:\ASES_AGENT_ROOT, Env:\ASES_TEST_PAT, Env:\ASES_TEST_PAUSE_BEFORE_RESULT_VALIDATE -ErrorAction SilentlyContinue

# ===== 3. Strict-validation vectors (direct runner, isolated) =====
$tr4 = New-TestRoot
function Test-Strict([string]$name, [string]$raw) {
    $opId = [guid]::NewGuid().ToString()
    New-Request $tr4 $opId $raw
    $r = Run-RunnerDirect $tr4 $opId $tr4
    Write-Output ("STRICT_$name exit=$($r.code)")
}
$base = '{"schema":"ases-agent-op-request/1","op_id":"{OPID}","op":"whoami","params":{},"created_utc":"{NOW}","expires_utc":"{EXP}","policy_sha256":"x"}'
$now = (Get-Date).ToUniversalTime().ToString('o'); $exp = (Get-Date).ToUniversalTime().AddMinutes(10).ToString('o')
$valid = $base.Replace('{OPID}','{OPID}').Replace('{NOW}',$now).Replace('{EXP}',$exp)
# valid (will run + succeed)
$opId=[guid]::NewGuid().ToString()
New-Request $tr4 $opId ($base.Replace('{OPID}',$opId).Replace('{NOW}',$now).Replace('{EXP}',$exp))
$r=Run-RunnerDirect $tr4 $opId $tr4
Write-Output ("STRICT_valid exit=$($r.code) (0=ran ok)")
# duplicate top-level key
$dup = $base.Replace('{OPID}','x').Replace('{NOW}',$now).Replace('{EXP}',$exp) -replace '"op":"whoami"', '"op":"whoami","op":"whoami"'
Test-Strict 'duplicate_key' $dup
# unknown key
$unk = $base.Replace('{OPID}','x').Replace('{NOW}',$now).Replace('{EXP}',$exp) -replace '"params":', '"extra":"z","params":'
Test-Strict 'unknown_key' $unk
# wrong-case key
$wc = $base.Replace('{OPID}','x').Replace('{NOW}',$now).Replace('{EXP}',$exp) -replace '"op":', '"Op":'
Test-Strict 'wrong_case_key' $wc
# malformed json
Test-Strict 'malformed' '{"schema":'
# BOM
$opId=[guid]::NewGuid().ToString()
$bom = [char]0xFEFF + $base.Replace('{OPID}',$opId).Replace('{NOW}',$now).Replace('{EXP}',$exp)
New-Request $tr4 $opId $bom
$r=Run-RunnerDirect $tr4 $opId $tr4
Write-Output ("STRICT_bom exit=$($r.code)")
# oversized (65537 bytes)
$opId=[guid]::NewGuid().ToString()
$big = $base.Replace('{OPID}',$opId).Replace('{NOW}',$now).Replace('{EXP}',$exp) -replace '"params":', ('"pad":"' + ('a' * 66000) + '","params":')
New-Request $tr4 $opId $big
$r=Run-RunnerDirect $tr4 $opId $tr4
Write-Output ("STRICT_oversized exit=$($r.code) (expected non-zero)")

Write-Output "FINAL_VERIFY_DONE"
