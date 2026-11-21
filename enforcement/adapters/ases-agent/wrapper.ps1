#Requires -Version 5.1
# ASES Rev3 Phase 1 — Wrapper (ases-op). Single-writer of the ledger.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Op,
    [Parameter(Position = 1)]
    [string]$ParamsJson = "{}"
)

$ErrorActionPreference = 'Continue'
$root = Join-Path $env:USERPROFILE '.ases-agent'
$runDir = Join-Path $root 'run'
$stateDir = Join-Path $root 'state'
$opsDir = Join-Path $stateDir 'ops'
$lockFile = Join-Path $stateDir 'lock'
$blockerFile = Join-Path $stateDir 'cleanup-blocker'
$policyPath = Join-Path $root 'config\policy.json'

function Get-UtcNow { (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ') }

function Get-FileSha256([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLower()
}

# ---- Load policy ----
if (-not (Test-Path -LiteralPath $policyPath)) { Write-Output 'POLICY_MISSING'; exit 20 }
$policy = Get-Content -LiteralPath $policyPath -Raw | ConvertFrom-Json
$policySha = Get-FileSha256 $policyPath

# ---- 1. Allowlist check ----
if ($policy.allowlist -notcontains $Op) { Write-Output "POLICY_DENIED: op not in allowlist: $Op"; exit 21 }

# ---- 2. pr-create NOT AUTHORIZED (FDR-5/FDR-7) ----
if ($Op -eq 'pr-create') { Write-Output 'POLICY_DENIED: pr-create NOT AUTHORIZED (FDR-5, FDR-7)'; exit 22 }

# ---- 3. Cleanup blocker check ----
if (Test-Path -LiteralPath $blockerFile) { Write-Output 'CLEANUP_FAILURE: blocker present'; exit 23 }

# ---- 4. Concurrency lock (exclusive-create) ----
try {
    $lockStream = [System.IO.File]::Open($lockFile, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    $lockStream.Close()
} catch {
    # orphan lock: if older than 15 min, still refuse (fail-closed per FDR-11) and report
    if (Test-Path -LiteralPath $lockFile) {
        $age = ((Get-Date) - (Get-Item -LiteralPath $lockFile).LastWriteTime).TotalMinutes
        if ($age -gt $policy.orphan_lock_minutes) { Write-Output "POLICY_DENIED: orphan lock present ($([int]$age)m > $($policy.orphan_lock_minutes)m); fail-closed"; exit 24 }
        Write-Output 'BUSY: another operation running'; exit 25
    }
    Write-Output "LOCK_ERROR: $($_.Exception.Message)"; exit 26
}
$lockContent = @{ op_id = ''; acquired_utc = Get-UtcNow } | ConvertTo-Json -Compress
[System.IO.File]::WriteAllText($lockFile, $lockContent)

try {
    # ---- 5. Params validation (basic: must be JSON object) ----
    $params = $null
    try { $params = $ParamsJson | ConvertFrom-Json } catch { Write-Output 'VALIDATION: params is not valid JSON'; exit 27 }

    # ---- 6. Create op_id + request file ----
    $opId = [guid]::NewGuid().ToString()
    $createdUtc = Get-UtcNow
    $expiresUtc = (Get-Date).ToUniversalTime().AddMinutes($policy.request_ttl_minutes).ToString('yyyy-MM-ddTHH:mm:ssZ')
    $request = @{
        schema = 'ases-agent-op-request/1'
        op_id = $opId
        op = $Op
        params = $params
        created_utc = $createdUtc
        expires_utc = $expiresUtc
        policy_sha256 = $policySha
    }
    $requestJson = $request | ConvertTo-Json -Depth 8 -Compress
    $requestPath = Join-Path $runDir "$opId.request.json"
    $tmp = "$requestPath.tmp"
    [System.IO.File]::WriteAllText($tmp, $requestJson, (New-Object System.Text.UTF8Encoding($false)))
    [System.IO.File]::Move($tmp, $requestPath)   # atomic replace
    $requestSha = Get-FileSha256 $requestPath

    # ---- 7. Ledger ADMITTED (single-writer: wrapper) ----
    $ledgerPath = Join-Path $opsDir "$opId.json"
    $ledger = @{ op_id = $opId; state = 'ADMITTED'; request_sha256 = $requestSha; op = $Op; created_utc = $createdUtc }
    $ledgerTmp = "$ledgerPath.tmp"
    [System.IO.File]::WriteAllText($ledgerTmp, ($ledger | ConvertTo-Json -Compress), (New-Object System.Text.UTF8Encoding($false)))
    [System.IO.File]::Move($ledgerTmp, $ledgerPath)

    # ---- 8. Launch interactive runner (pass ONLY op_id) ----
    $runnerPath = Join-Path $root 'runner.ps1'
    if (-not (Test-Path -LiteralPath $runnerPath)) { Write-Output 'RUNNER_MISSING'; exit 28 }
    $runnerArgs = @('-NoProfile','-ExecutionPolicy','Bypass','-File', $runnerPath, '-OpId', $opId)
    if ($env:ASES_TEST_PAT) { $runnerArgs += @('-TestPat', $env:ASES_TEST_PAT, '-UseMockGh') }
    $proc = Start-Process -FilePath 'powershell.exe' -ArgumentList $runnerArgs -PassThru -WindowStyle Normal

    # ---- 9. Wait for runner exit (execution timeout, FDR-10) ----
    $execTimeout = [TimeSpan]::FromMinutes($policy.execution_timeout_minutes)
    $waitOk = $proc.WaitForExit($execTimeout.TotalMilliseconds)
    if (-not $waitOk) {
        # timeout -> UNKNOWN (never FAILED/EXPIRED, no auto-retry)
        $ledger.state = 'UNKNOWN'; $ledger.note = 'execution_timeout_no_result'
        [System.IO.File]::WriteAllText($ledgerPath, ($ledger | ConvertTo-Json -Compress))
        Write-Output '{"state":"UNKNOWN","error_category":"TIMEOUT"}'
        exit 3
    }

    # ---- 10. Process result ----
    $resultPath = Join-Path $runDir "$opId.result.json"
    if (-not (Test-Path -LiteralPath $resultPath)) {
        $intentPath = Join-Path $runDir "$opId.intent"
        $claimPath = Join-Path $runDir "$opId.claimed"
        if (Test-Path -LiteralPath $intentPath) {
            $ledger.state = 'UNKNOWN'; $ledger.note = 'intent_recorded_no_result'
            [System.IO.File]::WriteAllText($ledgerPath, ($ledger | ConvertTo-Json -Compress))
            Write-Output '{"state":"UNKNOWN","error_category":"TIMEOUT"}'
            exit 3
        } else {
            $ledger.state = 'FAILED'; $ledger.note = 'runner_exit_no_result'
            [System.IO.File]::WriteAllText($ledgerPath, ($ledger | ConvertTo-Json -Compress))
            foreach ($p in @($requestPath, $claimPath)) { if (Test-Path -LiteralPath $p) { try { Remove-Item -LiteralPath $p -Force } catch {} } }
            Write-Output '{"state":"FAILED","error_category":"VALIDATION"}'
            exit 4
        }
    }

    # validate result
    $result = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json
    if ($result.op_id -ne $opId -or $result.request_sha256 -ne $requestSha) {
        $ledger.state = 'FAILED'; $ledger.note = 'result_mismatch'
        [System.IO.File]::WriteAllText($ledgerPath, ($ledger | ConvertTo-Json -Compress))
        Write-Output '{"state":"FAILED","error_category":"VALIDATION"}'
        exit 5
    }

    $ledger.state = $result.state
    $ledger.result_sha256 = Get-FileSha256 $resultPath
    $ledger.done_utc = Get-UtcNow
    [System.IO.File]::WriteAllText($ledgerPath, ($ledger | ConvertTo-Json -Compress))

    # ---- 11. Return result to Agent ----
    Write-Output ($result | ConvertTo-Json -Depth 8 -Compress)

    # ---- 12. Cleanup (idempotent) ----
    $cleanupStatus = 'OK'
    foreach ($p in @($requestPath, $resultPath, (Join-Path $runDir "$opId.claimed"), (Join-Path $runDir "$opId.intent"))) {
        if (Test-Path -LiteralPath $p) { try { Remove-Item -LiteralPath $p -Force } catch { $cleanupStatus = 'FAILED' } }
    }
    $ledger.cleanup_status = $cleanupStatus
    [System.IO.File]::WriteAllText($ledgerPath, ($ledger | ConvertTo-Json -Compress))
    if ($cleanupStatus -eq 'FAILED') {
        [System.IO.File]::WriteAllText($blockerFile, (Get-UtcNow))
        Write-Output '{"cleanup_status":"FAILED"}'
        exit 6
    }
    exit 0
}
finally {
    # release lock
    if (Test-Path -LiteralPath $lockFile) { try { Remove-Item -LiteralPath $lockFile -Force } catch {} }
}
