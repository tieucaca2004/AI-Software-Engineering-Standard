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
$CodeRoot = $PSScriptRoot
$ProductionRuntime = Join-Path $env:USERPROFILE '.ases-agent'

function Resolve-RuntimeRoot([string]$Override, [string]$Production) {
    $prod = [System.IO.Path]::GetFullPath($Production).TrimEnd('\')
    if ([string]::IsNullOrWhiteSpace($Override)) {
        return $prod
    }
    $canonical = [System.IO.Path]::GetFullPath($Override.Trim()).TrimEnd('\')
    if ($canonical -eq $prod) { throw 'ASES_AGENT_ROOT resolves to the production runtime; refused' }
    $walk = $canonical
    while ($walk) {
        $item = Get-Item -LiteralPath $walk -Force -ErrorAction SilentlyContinue
        if (-not $item) { throw "ASES_AGENT_ROOT path does not exist: $walk" }
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -eq [System.IO.FileAttributes]::ReparsePoint) {
            throw "ASES_AGENT_ROOT contains a reparse point/junction/symlink: $walk"
        }
        $parent = Split-Path -Parent $walk
        if ($parent -eq $walk) { break }
        $walk = $parent
    }
    if (-not (Test-Path -LiteralPath (Join-Path $canonical '.ases-agent-test-root'))) {
        throw 'ASES_AGENT_ROOT missing test-root sentinel (.ases-agent-test-root)'
    }
    foreach ($sub in @('run','state','config','logs')) {
        if (-not (Test-Path -LiteralPath (Join-Path $canonical $sub))) { throw "ASES_AGENT_ROOT missing subdirectory: $sub" }
    }
    return $canonical
}

$RuntimeRoot = Resolve-RuntimeRoot $env:ASES_AGENT_ROOT $ProductionRuntime
$runDir = Join-Path $RuntimeRoot 'run'
$stateDir = Join-Path $RuntimeRoot 'state'
$opsDir = Join-Path $stateDir 'ops'
$lockFile = Join-Path $stateDir 'lock'
$blockerFile = Join-Path $stateDir 'cleanup_failed'
$policyPath = Join-Path $RuntimeRoot 'config\policy.json'

# ---- Test-only hooks (fail-closed: require isolated test root) ----
$prodCanonical = [System.IO.Path]::GetFullPath($ProductionRuntime).TrimEnd('\')
$testCleanupFail = $false
$testPauseAfterRequest = $false
$testPauseBeforeResult = $false
$testEmptyPat = $false
if ($env:ASES_TEST_CLEANUP_FAIL -or $env:ASES_TEST_PAUSE_AFTER_REQUEST -or $env:ASES_TEST_PAUSE_BEFORE_RESULT_VALIDATE -or $env:ASES_TEST_EMPTY_PAT) {
    if ($RuntimeRoot -eq $prodCanonical) { throw 'test hook cannot target the production runtime' }
    if (-not (Test-Path -LiteralPath (Join-Path $RuntimeRoot '.ases-agent-test-root'))) { throw 'test hook requires the test-root sentinel' }
    $sentinelItem = Get-Item -LiteralPath (Join-Path $RuntimeRoot '.ases-agent-test-root') -Force -ErrorAction SilentlyContinue
    if (-not $sentinelItem) { throw 'test hook: sentinel missing' }
    if (($sentinelItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -eq [System.IO.FileAttributes]::ReparsePoint) { throw 'test hook: sentinel is a reparse point' }
    if ($env:ASES_TEST_CLEANUP_FAIL) { $testCleanupFail = $true }
    if ($env:ASES_TEST_PAUSE_AFTER_REQUEST) { $testPauseAfterRequest = $true }
    if ($env:ASES_TEST_PAUSE_BEFORE_RESULT_VALIDATE) { $testPauseBeforeResult = $true }
    if ($env:ASES_TEST_EMPTY_PAT) { $testEmptyPat = $true }
}

function Get-UtcNow { (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ') }

function Get-FileSha256([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLower()
}

function Get-Sha256Hex([byte[]]$Bytes) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($Bytes)) -replace '-', '').ToLower() }
    finally { $sha.Dispose() }
}

function Test-JsonDuplicateKeys([string]$Json) {
    $keyStacks = New-Object System.Collections.ArrayList
    $i = 0; $n = $Json.Length
    while ($i -lt $n) {
        $c = $Json[$i]
        if ($c -eq '"') {
            $i++
            $decoded = New-Object System.Text.StringBuilder
            while ($i -lt $n -and $Json[$i] -ne '"') {
                $ch = $Json[$i]
                if ($ch -eq '\') {
                    $i++
                    if ($i -ge $n) { break }
                    $esc = $Json[$i]
                    switch ($esc) {
                        'n' { [void]$decoded.Append("`n") }
                        't' { [void]$decoded.Append("`t") }
                        'r' { [void]$decoded.Append("`r") }
                        'b' { [void]$decoded.Append("`b") }
                        'f' { [void]$decoded.Append("`f") }
                        '"' { [void]$decoded.Append('"') }
                        '\' { [void]$decoded.Append('\') }
                        '/' { [void]$decoded.Append('/') }
                        'u' {
                            if ($i + 4 -lt $n) {
                                $hex = $Json.Substring($i + 1, 4)
                                try { [void]$decoded.Append([char][Convert]::ToInt32($hex, 16)) } catch {}
                                $i += 4
                            }
                        }
                    }
                } else { [void]$decoded.Append($ch) }
                $i++
            }
            $j = $i + 1
            while ($j -lt $n -and ($Json[$j] -eq ' ' -or $Json[$j] -eq "`t" -or $Json[$j] -eq "`r" -or $Json[$j] -eq "`n")) { $j++ }
            if ($j -lt $n -and $Json[$j] -eq ':') {
                $key = $decoded.ToString()
                if ($keyStacks.Count -gt 0) {
                    $top = $keyStacks[$keyStacks.Count - 1]
                    if ($top.ContainsKey($key)) { return $true }
                    $top[$key] = $true
                }
            }
        }
        elseif ($c -eq '{') { [void]$keyStacks.Add(@{}) }
        elseif ($c -eq '}') { if ($keyStacks.Count -gt 0) { $keyStacks.RemoveAt($keyStacks.Count - 1) } }
        $i++
    }
    return $false
}

function ConvertTo-CanonicalJson([object]$Value) {
    if ($null -eq $Value) { return 'null' }
    if ($Value -is [bool]) { return $(if ($Value) { 'true' } else { 'false' }) }
    if ($Value -is [string]) {
        $sb = New-Object System.Text.StringBuilder
        [void]$sb.Append('"')
        foreach ($ch in $Value.ToCharArray()) {
            switch ($ch) {
                '"'  { [void]$sb.Append('\"') }
                '\'  { [void]$sb.Append('\\') }
                "`b" { [void]$sb.Append('\b') }
                "`f" { [void]$sb.Append('\f') }
                "`n" { [void]$sb.Append('\n') }
                "`r" { [void]$sb.Append('\r') }
                "`t" { [void]$sb.Append('\t') }
                default { if ([int]$ch -lt 0x20) { [void]$sb.Append('\u' + ([int]$ch).ToString('x4')) } else { [void]$sb.Append($ch) } }
            }
        }
        [void]$sb.Append('"')
        return $sb.ToString()
    }
    if ($Value -is [System.Management.Automation.PSCustomObject]) {
        $ht = @{}
        foreach ($p in $Value.PSObject.Properties) { $ht[$p.Name] = $p.Value }
        return (ConvertTo-CanonicalJson $ht)
    }
    if ($Value -is [System.Collections.IDictionary]) {
        $sb = New-Object System.Text.StringBuilder
        [void]$sb.Append('{')
        $first = $true
        $keyArray = @($Value.Keys | ForEach-Object { [string]$_ })
        [System.Array]::Sort($keyArray, [System.StringComparer]::Ordinal)
        foreach ($k in $keyArray) {
            if (-not $first) { [void]$sb.Append(',') }
            [void]$sb.Append((ConvertTo-CanonicalJson $k))
            [void]$sb.Append(':')
            [void]$sb.Append((ConvertTo-CanonicalJson $Value[$k]))
            $first = $false
        }
        [void]$sb.Append('}')
        return $sb.ToString()
    }
    if ($Value -is [System.Collections.IEnumerable]) {
        $sb = New-Object System.Text.StringBuilder
        [void]$sb.Append('[')
        $first = $true
        foreach ($item in $Value) { if (-not $first) { [void]$sb.Append(',') }; [void]$sb.Append((ConvertTo-CanonicalJson $item)); $first = $false }
        [void]$sb.Append(']')
        return $sb.ToString()
    }
    if ($Value -is [double] -or $Value -is [single]) { return ([string]$Value).ToLowerInvariant() }
    if ($Value -is [int] -or $Value -is [long] -or $Value -is [decimal] -or $Value -is [byte]) { return [string]$Value }
    return (ConvertTo-CanonicalJson ([string]$Value))
}

function Get-ValidatedJson([string]$Path, [string[]]$AllowedKeys, [string[]]$RequiredKeys) {
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -gt 65536) { throw 'VALIDATION: oversized file' }
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) { throw 'VALIDATION: BOM present' }
    $strictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)
    $text = $null
    try { $text = $strictUtf8.GetString($bytes) } catch { throw 'VALIDATION: invalid UTF-8' }
    if (Test-JsonDuplicateKeys $text) { throw 'VALIDATION: duplicate key' }
    $obj = $null
    try { $obj = $text | ConvertFrom-Json } catch { throw 'VALIDATION: malformed JSON' }
    foreach ($p in $obj.PSObject.Properties) {
        if ($p.Name -cnotin $AllowedKeys) { throw "VALIDATION: unknown key: $($p.Name)" }
    }
    foreach ($k in $RequiredKeys) {
        if ($obj.PSObject.Properties.Name -cnotcontains $k) { throw "VALIDATION: missing key: $k" }
    }
    return $obj
}

function Test-UtcTimestamp([string]$s) {
    if ($s -isnot [string]) { return $false }
    if ($s -notmatch '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$') { return $false }
    $core = $s.Substring(0, $s.Length - 1)
    try { [void][datetime]::Parse($core, [System.Globalization.CultureInfo]::InvariantCulture, [System.Globalization.DateTimeStyles]::None); return $true }
    catch { return $false }
}

function Test-ResultFieldTypes($obj) {
    if ($obj.schema -isnot [string] -or $obj.schema -cne 'ases-agent-op-result/1') { return 'schema must be "ases-agent-op-result/1"' }
    if ($obj.op_id -isnot [string] -or $obj.op_id -notmatch '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') { return 'op_id must be a UUID v4' }
    if ($obj.request_sha256 -isnot [string] -or $obj.request_sha256 -notmatch '^[0-9a-f]{64}$') { return 'request_sha256 must be a 64-hex string' }
    if ($obj.state -isnot [string] -or $obj.state -cnotin @('SUCCEEDED','FAILED','DENIED','CANCELED','TIMEOUT','CLEANUP_FAILURE')) { return 'state must be a valid enum' }
    if ($obj.error_category -ne $null -and $obj.error_category -isnot [string]) { return 'error_category must be a string or null' }
    if ($obj.output -ne $null -and $obj.output -isnot [System.Management.Automation.PSCustomObject] -and $obj.output -isnot [System.Array]) { return 'output must be an object, array, or null' }
    if ($obj.completed_utc -isnot [string]) { return 'completed_utc must be a string' }
    if ($obj.cleanup_status -isnot [string] -or $obj.cleanup_status -cnotin @('OK','FAILED')) { return 'cleanup_status must be OK or FAILED' }
    if ($obj.result_sha256 -isnot [string] -or $obj.result_sha256 -notmatch '^[0-9a-f]{64}$') { return 'result_sha256 must be a 64-hex string' }
    if (-not (Test-UtcTimestamp $obj.completed_utc)) { return 'completed_utc must be ISO-8601 UTC (Z)' }
    return $null
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
    [System.IO.File]::Move($tmp, $requestPath)
    $requestSha = Get-FileSha256 $requestPath

    # ---- 7. Ledger ADMITTED (single-writer: wrapper) ----
    $ledgerPath = Join-Path $opsDir "$opId.json"
    $ledger = @{ op_id = $opId; state = 'ADMITTED'; request_sha256 = $requestSha; op = $Op; created_utc = $createdUtc }
    $ledgerTmp = "$ledgerPath.tmp"
    [System.IO.File]::WriteAllText($ledgerTmp, ($ledger | ConvertTo-Json -Compress), (New-Object System.Text.UTF8Encoding($false)))
    [System.IO.File]::Move($ledgerTmp, $ledgerPath)

    # ---- 7b. Test pause hook A (request tampering window) ----
    if ($testPauseAfterRequest) {
        [System.IO.File]::WriteAllText((Join-Path $runDir "$opId.pause-after-request"), '1', (New-Object System.Text.UTF8Encoding($false)))
        for ($w = 0; $w -lt 60 -and (Test-Path -LiteralPath (Join-Path $runDir "$opId.pause-after-request")); $w++) { Start-Sleep -Milliseconds 500 }
    }

    # ---- 8. Launch interactive runner (pass op_id + authorized RuntimeRoot) ----
    $runnerPath = Join-Path $CodeRoot 'runner.ps1'
    if (-not (Test-Path -LiteralPath $runnerPath)) { Write-Output 'RUNNER_MISSING'; exit 28 }
    $runnerArgs = @('-NoProfile','-ExecutionPolicy','Bypass','-File', $runnerPath, '-OpId', $opId, '-RuntimeRoot', $RuntimeRoot)
    if ($testEmptyPat) { $runnerArgs += @('-EmptyPat', '-UseMockGh') }
    elseif ($env:ASES_TEST_PAT) { $runnerArgs += @('-TestPat', $env:ASES_TEST_PAT, '-UseMockGh') }
    $proc = Start-Process -FilePath 'powershell.exe' -ArgumentList $runnerArgs -PassThru -WindowStyle Normal

    # ---- 9. Wait for runner exit (execution timeout, FDR-10) ----
    $execTimeout = [TimeSpan]::FromMinutes($policy.execution_timeout_minutes)
    $waitOk = $proc.WaitForExit($execTimeout.TotalMilliseconds)
    if (-not $waitOk) {
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

    # ---- 10b. Test pause hook B (result tampering window) ----
    if ($testPauseBeforeResult) {
        [System.IO.File]::WriteAllText((Join-Path $runDir "$opId.pause-before-result"), '1', (New-Object System.Text.UTF8Encoding($false)))
        for ($w = 0; $w -lt 60 -and (Test-Path -LiteralPath (Join-Path $runDir "$opId.pause-before-result")); $w++) { Start-Sleep -Milliseconds 500 }
    }

    # ---- validate result (strict + result_sha256) ----
    $result = $null
    try {
        $result = Get-ValidatedJson $resultPath @('schema','op_id','request_sha256','state','error_category','output','completed_utc','cleanup_status','result_sha256') @('schema','op_id','request_sha256','state','error_category','output','completed_utc','cleanup_status','result_sha256')
    } catch {
        $ledger.state = 'FAILED'; $ledger.note = $_.Exception.Message
        [System.IO.File]::WriteAllText($ledgerPath, ($ledger | ConvertTo-Json -Compress))
        Write-Output '{"state":"FAILED","error_category":"VALIDATION"}'
        exit 5
    }
    if (Test-ResultFieldTypes $result) {
        $ledger.state = 'FAILED'; $ledger.note = 'result_type_invalid'
        [System.IO.File]::WriteAllText($ledgerPath, ($ledger | ConvertTo-Json -Compress))
        Write-Output '{"state":"FAILED","error_category":"VALIDATION"}'
        exit 5
    }
    if ($result.op_id -ne $opId -or $result.request_sha256 -ne $requestSha) {
        $ledger.state = 'FAILED'; $ledger.note = 'result_mismatch'
        [System.IO.File]::WriteAllText($ledgerPath, ($ledger | ConvertTo-Json -Compress))
        Write-Output '{"state":"FAILED","error_category":"VALIDATION"}'
        exit 5
    }
    $resultWithoutHash = @{}
    foreach ($p in $result.PSObject.Properties) { if ($p.Name -ne 'result_sha256') { $resultWithoutHash[$p.Name] = $p.Value } }
    $canonicalResult = ConvertTo-CanonicalJson $resultWithoutHash
    $computedResultHash = Get-Sha256Hex ([System.Text.Encoding]::UTF8.GetBytes($canonicalResult))
    if ($result.result_sha256 -cne $computedResultHash) {
        $ledger.state = 'FAILED'; $ledger.note = 'result_hash_mismatch'
        [System.IO.File]::WriteAllText($ledgerPath, ($ledger | ConvertTo-Json -Compress))
        Write-Output '{"state":"FAILED","error_category":"VALIDATION"}'
        exit 5
    }

    $ledger.state = $result.state
    $ledger.result_sha256 = $result.result_sha256
    $ledger.done_utc = Get-UtcNow
    [System.IO.File]::WriteAllText($ledgerPath, ($ledger | ConvertTo-Json -Compress))

    # ---- 11. Return result to Agent ----
    Write-Output ($result | ConvertTo-Json -Depth 8 -Compress)

    # ---- 12. Cleanup (idempotent; fault-injectable) ----
    $cleanupStatus = 'OK'
    $failInjected = $false
    foreach ($p in @($requestPath, $resultPath, (Join-Path $runDir "$opId.claimed"), (Join-Path $runDir "$opId.intent"))) {
        if (Test-Path -LiteralPath $p) {
            if ($testCleanupFail -and -not $failInjected) { $failInjected = $true; $cleanupStatus = 'FAILED'; continue }
            try { Remove-Item -LiteralPath $p -Force } catch { $cleanupStatus = 'FAILED' }
        }
    }
    $ledger.cleanup_status = $cleanupStatus
    [System.IO.File]::WriteAllText($ledgerPath, ($ledger | ConvertTo-Json -Compress))
    if ($cleanupStatus -eq 'FAILED') {
        [System.IO.File]::WriteAllText($blockerFile, (Get-UtcNow))
        Write-Output '{"cleanup_status":"FAILED","error_category":"CLEANUP_FAILURE"}'
        exit 6
    }
    exit 0
}
finally {
    if (Test-Path -LiteralPath $lockFile) { try { Remove-Item -LiteralPath $lockFile -Force } catch {} }
}
