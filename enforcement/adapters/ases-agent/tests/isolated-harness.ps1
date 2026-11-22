# ASES Rev3 — Milestone 2 isolated launcher + Phase 1 test harness.
# Runs against a fresh temp RuntimeRoot via the CANONICAL wrapper (never runner.ps1 directly).
$ErrorActionPreference = 'Continue'
$repo = 'D:\AI\ASES-DeepSeek'
$adapter = Join-Path $repo 'enforcement\adapters\ases-agent'
$wrapper = Join-Path $adapter 'wrapper.ps1'
$productionRuntime = Join-Path $env:USERPROFILE '.ases-agent'

$results = New-Object System.Collections.ArrayList

# ---------- 1. Create isolated RuntimeRoot ----------
$testRoot = Join-Path $env:TEMP ("ases-agent-test-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path (Join-Path $testRoot 'run'), (Join-Path $testRoot 'state\ops'), (Join-Path $testRoot 'config'), (Join-Path $testRoot 'logs') | Out-Null | Out-Null
[System.IO.File]::WriteAllText((Join-Path $testRoot '.ases-agent-test-root'), 'test-root-sentinel', (New-Object System.Text.UTF8Encoding($false)))
Copy-Item -LiteralPath (Join-Path $adapter 'config\policy.json') -Destination (Join-Path $testRoot 'config\policy.json') -Force

# ---------- 2. Isolation proof ----------
$canonicalTest = [System.IO.Path]::GetFullPath($testRoot).TrimEnd('\')
$canonicalProd = [System.IO.Path]::GetFullPath($productionRuntime).TrimEnd('\')
$isolation = @{
    TestRoot = $canonicalTest
    ProductionRoot = $canonicalProd
    IsDistinct = ($canonicalTest -ne $canonicalProd)
    SentinelPresent = (Test-Path -LiteralPath (Join-Path $testRoot '.ases-agent-test-root'))
    RequiredDirsPresent = ((@('run','state','config','logs') | ForEach-Object { Test-Path -LiteralPath (Join-Path $testRoot $_) }) -notcontains $false)
}

# snapshot production runtime (must be unchanged at end)
$prodSnapshot = @{}
Get-ChildItem -Recurse -File $productionRuntime -ErrorAction SilentlyContinue | ForEach-Object { $prodSnapshot[$_.FullName] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }

# ---------- helpers ----------
function Invoke-Wrapper([string]$Op, [string]$ParamsJson, [hashtable]$Mock) {
    $env:ASES_AGENT_ROOT = $canonicalTest
    $env:ASES_TEST_PAT = 'fake-test-pat-isolated-0000'
    foreach ($k in $Mock.Keys) { Set-Item -Path "Env:$k" -Value $Mock[$k] }
    $out = & powershell -NoProfile -ExecutionPolicy Bypass -File $wrapper $Op $ParamsJson 2>&1 | Out-String
    $code = $LASTEXITCODE
    Remove-Item Env:\ASES_AGENT_ROOT, Env:\ASES_TEST_PAT -ErrorAction SilentlyContinue
    foreach ($k in $Mock.Keys) { Remove-Item -Path "Env:$k" -ErrorAction SilentlyContinue }
    return @{ code = $code; out = $out }
}

function Add-Result([string]$Id, [string]$Status, [string]$Detail) {
    [void]$script:results.Add([pscustomobject]@{ Test=$Id; Status=$Status; Detail=$Detail; Utc=(Get-Date).ToUniversalTime().ToString('o') })
}

# ---------- T01: identity ----------
$r = Invoke-Wrapper 'whoami' '{}' @{}
Add-Result 'T01' $(if ($r.out -match 'chautinhtinh3979' -and $r.out -match 'SUCCEEDED') { 'PASS' } else { 'FAIL' }) ("exit=$($r.code)")

# ---------- T02: identity mismatch ----------
$r = Invoke-Wrapper 'whoami' '{}' @{ MOCK_LOGIN = 'tieucaca2004' }
Add-Result 'T02' $(if ($r.out -match 'IDENTITY_MISMATCH') { 'PASS' } else { 'FAIL' }) ("exit=$($r.code)")

# ---------- T03: empty PAT -> AUTH_MISSING (isolated injection hook) ----------
$r = Invoke-Wrapper 'whoami' '{}' @{ ASES_TEST_EMPTY_PAT = '1' }
Add-Result 'T03' $(if ($r.out -match 'AUTH_MISSING') { 'PASS' } else { 'FAIL' }) ("exit=$($r.code) empty-PAT injection -> AUTH_MISSING")

# ---------- T04: invalid PAT -> AUTH_INVALID ----------
$r = Invoke-Wrapper 'whoami' '{}' @{ MOCK_AUTH_FAIL = '401' }
Add-Result 'T04' $(if ($r.out -match 'AUTH_INVALID') { 'PASS' } else { 'FAIL' }) ("exit=$($r.code)")

# ---------- T05: gh config + credential state unchanged ----------
$cfgBefore = (Get-FileHash -LiteralPath "$env:APPDATA\GitHub CLI\config.yml","$env:APPDATA\GitHub CLI\hosts.yml" -Algorithm SHA256 -ErrorAction SilentlyContinue).Hash
$cmdBefore = (cmdkey /list 2>&1 | Select-String -Pattern 'Target:' | ForEach-Object { $_.Line.Trim() }) -join ';'
$r = Invoke-Wrapper 'whoami' '{}' @{}
$cfgAfter = (Get-FileHash -LiteralPath "$env:APPDATA\GitHub CLI\config.yml","$env:APPDATA\GitHub CLI\hosts.yml" -Algorithm SHA256 -ErrorAction SilentlyContinue).Hash
$cmdAfter = (cmdkey /list 2>&1 | Select-String -Pattern 'Target:' | ForEach-Object { $_.Line.Trim() }) -join ';'
Add-Result 'T05' $(if (($cfgBefore -join '|') -eq ($cfgAfter -join '|') -and $cmdBefore -eq $cmdAfter) { 'PASS' } else { 'FAIL' }) 'config-hash + credential-manager names unchanged'

# ---------- T16: secret scan of test root ----------
$patterns = 'ghp_[A-Za-z0-9]{20,}','github_pat_[A-Za-z0-9]{20,}','gho_[A-Za-z0-9]{20,}'
$found = @(); $scanned = @(); $unreadable = @()
Get-ChildItem -Recurse -File $testRoot -ErrorAction SilentlyContinue | ForEach-Object {
    $scanned += $_.FullName
    $c = Get-Content -LiteralPath $_.FullName -Raw -ErrorAction SilentlyContinue
    if (-not $c) { $unreadable += $_.FullName; return }
    foreach ($p in $patterns) { if ($c -match $p) { $found += "$($_.FullName):$p" } }
}
Add-Result 'T16' $(if ($found.Count -eq 0) { 'PASS' } else { 'FAIL' }) ("scanned=$($scanned.Count) unreadable=$($unreadable.Count) matches=$($found.Count)")

# ---------- T17: cleanup-failure injection + blocker rejection ----------
# (a) inject a cleanup failure through the isolated-only fault hook (ASES_TEST_CLEANUP_FAIL=1)
$env:ASES_AGENT_ROOT = $canonicalTest
$env:ASES_TEST_PAT = 'fake-test-pat-isolated-0000'
$env:ASES_TEST_CLEANUP_FAIL = '1'
$t17a = & powershell -NoProfile -ExecutionPolicy Bypass -File $wrapper 'whoami' '{}' 2>&1 | Out-String
$t17aCode = $LASTEXITCODE
Remove-Item Env:\ASES_TEST_CLEANUP_FAIL -ErrorAction SilentlyContinue
$t17blocker = Test-Path -LiteralPath (Join-Path $testRoot 'state\cleanup_failed')
# (b) subsequent operation must be rejected while the cleanup_failed blocker exists
$t17b = & powershell -NoProfile -ExecutionPolicy Bypass -File $wrapper 'whoami' '{}' 2>&1 | Out-String
$t17bCode = $LASTEXITCODE
Remove-Item Env:\ASES_AGENT_ROOT, Env:\ASES_TEST_PAT -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $testRoot 'state\cleanup_failed') -Force -ErrorAction SilentlyContinue
$t17ok = ($t17a -match 'CLEANUP_FAILURE') -and $t17blocker -and ($t17b -match 'CLEANUP_FAILURE')
Add-Result 'T17' $(if ($t17ok) { 'PASS' } else { 'FAIL' }) ("inject_exit=$t17aCode failure=$($t17a -match 'CLEANUP_FAILURE') blocker=$t17blocker reject_exit=$t17bCode")

# ---------- T21: token expiry warning (<=14d) ----------
$expiry5 = (Get-Date).ToUniversalTime().AddDays(5).ToString('yyyy-MM-ddTHH:mm:ssZ')
$r = Invoke-Wrapper 'whoami' '{}' @{ MOCK_TOKEN_EXPIRY = $expiry5 }
$t21obj = $null
try { $t21obj = ($r.out.Trim() | ConvertFrom-Json) } catch { $t21obj = $null }
$t21warn = ($t21obj -and $t21obj.output.token_expiry_warning -eq $true)
$t21days = ($t21obj -and $t21obj.output.token_days_left -le 5)
Add-Result 'T21' $(if ($t21warn -and $t21days) { 'PASS' } else { 'FAIL' }) "expiry=5d warning=$t21warn days=$($t21obj.output.token_days_left)"

# ---------- T25: wrapper-level validation + result tampering ----------
$r1 = Invoke-Wrapper 'api' '{}' @{}
$r2 = Invoke-Wrapper 'pr-create' '{}' @{}
$r3 = Invoke-Wrapper 'pr-list' 'not-json{' @{}
# T25d: result tampering via the pause-before-result hook -> wrapper rejects (exit 5)
$env:ASES_AGENT_ROOT = $canonicalTest
$env:ASES_TEST_PAT = 'fake-test-pat-isolated-0000'
$env:ASES_TEST_PAUSE_BEFORE_RESULT_VALIDATE = '1'
$t25wp = Start-Process powershell.exe -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',$wrapper,'whoami','{}') -PassThru -WindowStyle Hidden
$t25marker = $null
for ($i=0; $i -lt 40; $i++) { Start-Sleep -Milliseconds 500; $m = Get-ChildItem (Join-Path $canonicalTest 'run') -Filter '*.pause-before-result' -ErrorAction SilentlyContinue | Select-Object -First 1; if ($m) { $t25marker = $m; break } }
$t25tamper = $false
if ($t25marker) {
    $t25op = $t25marker.BaseName -replace '\.pause-before-result$',''
    $t25rp = Join-Path $canonicalTest "run\$t25op.result.json"
    $t25c = Get-Content -LiteralPath $t25rp -Raw
    $t25c2 = $t25c -replace '"login":"chautinhtinh3979"', '"login":"tampered"'
    [System.IO.File]::WriteAllText($t25rp, $t25c2, (New-Object System.Text.UTF8Encoding($false)))
    Remove-Item -LiteralPath $t25marker.FullName -Force
}
$t25wp.WaitForExit(25000) | Out-Null
$t25tamper = ($t25wp.ExitCode -eq 5)
Remove-Item Env:\ASES_AGENT_ROOT, Env:\ASES_TEST_PAT, Env:\ASES_TEST_PAUSE_BEFORE_RESULT_VALIDATE -ErrorAction SilentlyContinue
$t25ok = ($r1.out -match 'POLICY_DENIED') -and ($r2.out -match 'NOT AUTHORIZED') -and ($r3.out -match 'VALIDATION') -and $t25tamper
Add-Result 'T25' $(if ($t25ok) { 'PARTIAL' } else { 'FAIL' }) ("wrapper validation + result-tamper; tamper_rejected=$t25tamper; request-tamper + remaining S14 cases in dedicated scripts")

# ---------- T26: two consecutive ops (per-op PAT via mock; no leftover) ----------
$r = Invoke-Wrapper 'whoami' '{}' @{}
$r2 = Invoke-Wrapper 'repo-permissions' '{}' @{}
$ghTokenLeft = [bool](Get-ChildItem Env:GH_TOKEN -ErrorAction SilentlyContinue)
Add-Result 'T26' $(if ($r.out -match 'SUCCEEDED' -and $r2.out -match 'SUCCEEDED' -and -not $ghTokenLeft) { 'PARTIAL' } else { 'FAIL' }) 'two ops; interactive cancel/timeout NOT exercised'

# ---------- production runtime unchanged check ----------
$prodChanged = @()
foreach ($k in $prodSnapshot.Keys) {
    if (Test-Path -LiteralPath $k) {
        if ((Get-FileHash -LiteralPath $k -Algorithm SHA256).Hash -ne $prodSnapshot[$k]) { $prodChanged += $k }
    } else { $prodChanged += "$k (deleted)" }
}
Add-Result 'PRODUCTION-ISOLATION' $(if ($prodChanged.Count -eq 0) { 'PASS' } else { 'FAIL' }) ("prod_files_changed=$($prodChanged.Count)")

# ---------- evidence dump ----------
$ledgerFiles = Get-ChildItem -Recurse -File (Join-Path $testRoot 'state\ops') -ErrorAction SilentlyContinue
$report = @{
    test_root = $canonicalTest
    isolation = $isolation
    results = $results
    ledger_records = @($ledgerFiles | ForEach-Object { Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json })
}
$reportPath = Join-Path $testRoot 'report.json'
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding UTF8

# ---------- human summary ----------
Write-Output "===== MILESTONE 2 ISOLATED HARNESS ====="
Write-Output ("TEST_ROOT=" + $canonicalTest)
Write-Output ("ISOLATION_DISTINCT=" + $isolation.IsDistinct + " SENTINEL=" + $isolation.SentinelPresent + " DIRS=" + $isolation.RequiredDirsPresent)
$results | Format-Table -AutoSize | Out-String | Write-Output
Write-Output ("REPORT=" + $reportPath)
Write-Output "HARNESS_DONE"
