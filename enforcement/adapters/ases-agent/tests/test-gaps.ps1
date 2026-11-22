# Targeted regression: T03 (AUTH_MISSING), T04 (AUTH_INVALID), T21 (token expiry).
$ErrorActionPreference = 'Continue'
$root = $env:ASES_AGENT_ROOT
if (-not $root) { Write-Output 'REFUSE: ASES_AGENT_ROOT not set; legacy tests require an isolated test root (never production)'; exit 90 }
if (-not (Test-Path -LiteralPath (Join-Path $root '.ases-agent-test-root'))) { Write-Output 'REFUSE: isolated test-root sentinel (.ases-agent-test-root) missing'; exit 90 }
$runner = Join-Path $root 'runner.ps1'
$runDir = Join-Path $root 'run'

function New-Request([string]$opId) {
    $req = @{ schema='ases-agent-op-request/1'; op_id=$opId; op='whoami'; params=@{}; created_utc=(Get-Date).ToUniversalTime().ToString('o'); expires_utc=(Get-Date).ToUniversalTime().AddMinutes(10).ToString('o'); policy_sha256='test-policy-hash' } | ConvertTo-Json -Compress
    [System.IO.File]::WriteAllText((Join-Path $runDir "$opId.request.json"), $req, (New-Object System.Text.UTF8Encoding($false)))
}

function Run-Runner([string]$opId, [string]$testPat, [bool]$mock) {
    New-Request $opId
    $argList = @('-NoProfile','-ExecutionPolicy','Bypass','-File', $runner, '-OpId', $opId, '-TestPat', $testPat)
    if ($mock) { $argList += '-UseMockGh' }
    $out = & powershell @argList 2>&1 | Out-String
    $code = $LASTEXITCODE
    return @{ code=$code; out=$out }
}

# T03: empty PAT -> AUTH_MISSING
$op1 = [guid]::NewGuid().ToString()
$r1 = Run-Runner $op1 '' $true
$res1 = if (Test-Path "$runDir\$op1.result.json") { Get-Content "$runDir\$op1.result.json" -Raw | ConvertFrom-Json } else { $null }
Write-Output ("T03_EMPTY_PAT state={0} error={1} => {2}" -f $res1.state, $res1.error_category, (($res1.state -eq 'CANCELED') -and ($res1.error_category -eq 'AUTH_MISSING')))

# T04: 401 -> AUTH_INVALID
$env:MOCK_AUTH_FAIL = '401'
$op2 = [guid]::NewGuid().ToString()
$r2 = Run-Runner $op2 'any-token' $true
$res2 = if (Test-Path "$runDir\$op2.result.json") { Get-Content "$runDir\$op2.result.json" -Raw | ConvertFrom-Json } else { $null }
Write-Output ("T04_AUTH_401 state={0} error={1} => {2}" -f $res2.state, $res2.error_category, (($res2.state -eq 'FAILED') -and ($res2.error_category -eq 'AUTH_INVALID')))
Remove-Item Env:\MOCK_AUTH_FAIL -ErrorAction SilentlyContinue

# T21: expiry 5 days (<=14) -> warning
$op3 = [guid]::NewGuid().ToString()
$env:MOCK_TOKEN_EXPIRY = (Get-Date).ToUniversalTime().AddDays(5).ToString('yyyy-MM-ddTHH:mm:ssZ')
$r3 = Run-Runner $op3 'tok' $true
Write-Output ("T21_5DAYS warning={0}" -f ($r3.out -match 'WARNING: token expires'))
Remove-Item Env:\MOCK_TOKEN_EXPIRY -ErrorAction SilentlyContinue

# T21: expiry 30 days (>14) -> no warning
$op4 = [guid]::NewGuid().ToString()
$env:MOCK_TOKEN_EXPIRY = (Get-Date).ToUniversalTime().AddDays(30).ToString('yyyy-MM-ddTHH:mm:ssZ')
$r4 = Run-Runner $op4 'tok' $true
Write-Output ("T21_30DAYS no_warning={0}" -f ($r4.out -notmatch 'WARNING: token expires'))
Remove-Item Env:\MOCK_TOKEN_EXPIRY -ErrorAction SilentlyContinue

# T21: missing expiry -> unavailable warning
$op5 = [guid]::NewGuid().ToString()
$r5 = Run-Runner $op5 'tok' $true
Write-Output ("T21_MISSING unavailable_warning={0}" -f ($r5.out -match 'expiry metadata unavailable'))

Write-Output "GAPS_TEST_DONE"
