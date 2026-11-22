# Controlled durability test: kill runner AFTER intent durable-flush, BEFORE any external effect.
$ErrorActionPreference = 'Continue'
$root = $env:ASES_AGENT_ROOT
if (-not $root) { Write-Output 'REFUSE: ASES_AGENT_ROOT not set; legacy tests require an isolated test root (never production)'; exit 90 }
if (-not (Test-Path -LiteralPath (Join-Path $root '.ases-agent-test-root'))) { Write-Output 'REFUSE: isolated test-root sentinel (.ases-agent-test-root) missing'; exit 90 }
$wrapper = Join-Path $root 'wrapper.ps1'
$runDir = Join-Path $root 'run'
$opsDir = Join-Path $root 'state\ops'

# Pre-existing op ids (residual + regression) — must NOT be touched.
$preOps = @('970fd852-b9a0-4e72-8464-be8eb33d9223','de77bfd6-6a36-430c-a98e-be2025bd8c14','f41a1d48-51c7-4bd4-8e3d-0003381954d9','23c85407-839f-47f7-babb-8d0b2e9fa6c9','47fb7da5-76e0-4760-80b1-8fb21ceeb88d','64321e82-d261-4ac0-b6cc-87197cf9c012')
$existingIntents = @(Get-ChildItem "$runDir\*.intent" -ErrorAction SilentlyContinue | ForEach-Object Name)

# fault-injection env (mock gh sleeps 40s on identity verify)
$env:MOCK_SLEEP_SECONDS = '40'
$env:ASES_TEST_PAT = 'durability-test-pat-0002'

# launch wrapper in background (hidden window)
$wproc = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File', $wrapper, 'whoami') -PassThru -WindowStyle Hidden
Write-Output ("WRAPPER_PID=" + $wproc.Id)

# poll for NEW intent (durable-flushed) up to 30s
$newIntent = $null
for ($i=0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    $newIntent = @(Get-ChildItem "$runDir\*.intent" -ErrorAction SilentlyContinue | Where-Object { $_.Name -notin $existingIntents })
    if ($newIntent.Count -gt 0) { break }
}
Write-Output ("NEW_INTENT_DETECTED=" + (@($newIntent | ForEach-Object Name) -join ','))

if ($newIntent.Count -gt 0) {
    # kill the runner (powershell running runner.ps1, not the wrapper)
    $runners = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match 'runner\.ps1' -and $_.ProcessId -ne $wproc.Id })
    Write-Output ("RUNNER_PIDS=" + (@($runners | ForEach-Object ProcessId) -join ','))
    foreach ($r in $runners) { Stop-Process -Id $r.ProcessId -Force -ErrorAction SilentlyContinue }
    Write-Output "RUNNER_KILLED"
}

# wait for wrapper to finish (should classify UNKNOWN after runner killed)
$wproc.WaitForExit(20000) | Out-Null
Write-Output ("WRAPPER_EXITED=" + $wproc.HasExited)

# evidence
$intentPath = if ($newIntent.Count -gt 0) { $newIntent[0].FullName }
Write-Output ("INTENT_SURVIVES_AFTER_KILL=" + ($intentPath -and (Test-Path -LiteralPath $intentPath)))
if ($intentPath) { Write-Output ("INTENT_SIZE=" + (Get-Item -LiteralPath $intentPath).Length + " CONTENT=" + (Get-Content -LiteralPath $intentPath -Raw).Trim()) }

$newLedger = @(Get-ChildItem "$opsDir\*.json" -ErrorAction SilentlyContinue | Where-Object { $_.BaseName -notin $preOps })
foreach ($l in $newLedger) {
    $c = Get-Content -LiteralPath $l.FullName -Raw | ConvertFrom-Json
    Write-Output ("NEW_LEDGER={0} state={1} note={2}" -f $l.BaseName, $c.state, $c.note)
}

$newResult = @(Get-ChildItem "$runDir\*.result.json" -ErrorAction SilentlyContinue | Where-Object { $_.BaseName -notin $preOps })
Write-Output ("NEW_RESULT_COUNT=" + $newResult.Count + "  (0 = no result, correct)")

$newClaim = @(Get-ChildItem "$runDir\*.claimed" -ErrorAction SilentlyContinue | Where-Object { $_.BaseName -notin $preOps })
Write-Output ("NEW_CLAIM_RETAINED=" + (@($newClaim | ForEach-Object Name) -join ','))

Write-Output "DURABILITY_TEST_DONE"
