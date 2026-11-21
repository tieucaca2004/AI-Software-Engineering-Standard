# F1–F5 verification: endpoint mapping, error classification, exit-code validation, whoami schema.
$ErrorActionPreference = 'Continue'
$root = Join-Path $env:USERPROFILE '.ases-agent'
$runner = Join-Path $root 'runner.ps1'
$runDir = Join-Path $root 'run'

function Run-Op([string]$op, $params, [hashtable]$envVars) {
    foreach ($k in $envVars.Keys) { Set-Item -Path "Env:$k" -Value $envVars[$k] }
    $opId = [guid]::NewGuid().ToString()
    $req = @{ schema='ases-agent-op-request/1'; op_id=$opId; op=$op; params=$params; created_utc=(Get-Date).ToUniversalTime().ToString('o'); expires_utc=(Get-Date).ToUniversalTime().AddMinutes(10).ToString('o'); policy_sha256='test' } | ConvertTo-Json -Depth 6 -Compress
    [System.IO.File]::WriteAllText((Join-Path $runDir "$opId.request.json"), $req, (New-Object System.Text.UTF8Encoding($false)))
    $out = & powershell -NoProfile -ExecutionPolicy Bypass -File $runner -OpId $opId -TestPat 'tok' -UseMockGh 2>&1 | Out-String
    $code = $LASTEXITCODE
    $res = if (Test-Path "$runDir\$opId.result.json") { Get-Content "$runDir\$opId.result.json" -Raw | ConvertFrom-Json } else { $null }
    foreach ($k in $envVars.Keys) { Remove-Item -Path "Env:$k" -ErrorAction SilentlyContinue }
    return @{ code=$code; res=$res; out=$out }
}

$e = @{}

# F1/F5: whoami structured output
$r = Run-Op 'whoami' @{} @{ MOCK_TOKEN_EXPIRY = (Get-Date).ToUniversalTime().AddDays(5).ToString('yyyy-MM-ddTHH:mm:ssZ') }
Write-Output ("F5_whoami_schema: state={0} login={1} scope={2} has_expiry={3} has_days={4} warning={5}" -f $r.res.state, $r.res.output.login, $r.res.output.scope, [bool]$r.res.output.token_expiry_utc, ($r.res.output.token_days_left -ne $null), $r.res.output.token_expiry_warning)
Write-Output ("  PASS=" + (($r.res.state -eq 'SUCCEEDED') -and ($r.res.output.login -eq 'chautinhtinh3979') -and ($r.res.output.scope -eq 'repo') -and ($r.res.output.token_expiry_warning -eq $true)))

# F1: repo-permissions
$r = Run-Op 'repo-permissions' @{} $e
Write-Output ("F1_repo-permissions: state={0} permission={1}" -f $r.res.state, $r.res.output.permission)
Write-Output ("  PASS=" + (($r.res.state -eq 'SUCCEEDED') -and ($r.res.output.permission -eq 'write')))

# F1: pr-list
$r = Run-Op 'pr-list' @{ state='open'; limit=10 } $e
Write-Output ("F1_pr-list: state={0} count={1}" -f $r.res.state, @($r.res.output).Count)
Write-Output ("  PASS=" + ($r.res.state -eq 'SUCCEEDED'))

# F1: pr-view
$r = Run-Op 'pr-view' @{ number=1 } $e
Write-Output ("F1_pr-view: state={0} number={1}" -f $r.res.state, $r.res.output.number)
Write-Output ("  PASS=" + ($r.res.state -eq 'SUCCEEDED'))

# F1: pr-checks
$r = Run-Op 'pr-checks' @{ number=1 } $e
Write-Output ("F1_pr-checks: state={0} check_runs={1}" -f $r.res.state, @($r.res.output.check_runs).Count)
Write-Output ("  PASS=" + ($r.res.state -eq 'SUCCEEDED'))

# F2: 401 -> AUTH_INVALID
$r = Run-Op 'whoami' @{} @{ MOCK_AUTH_FAIL='401' }
Write-Output ("F2_401: error={0}" -f $r.res.error_category)
Write-Output ("  PASS=" + ($r.res.error_category -eq 'AUTH_INVALID'))

# F2: scope mismatch -> SCOPE_MISMATCH
$r = Run-Op 'whoami' @{} @{ MOCK_SCOPE='read:user' }
Write-Output ("F2_scope: error={0}" -f $r.res.error_category)
Write-Output ("  PASS=" + ($r.res.error_category -eq 'SCOPE_MISMATCH'))

# F2/F3: network -> NETWORK
$r = Run-Op 'whoami' @{} @{ MOCK_NETWORK_FAIL='1' }
Write-Output ("F3_network: error={0}" -f $r.res.error_category)
Write-Output ("  PASS=" + ($r.res.error_category -eq 'NETWORK'))

# F3: 404 -> GITHUB_4XX
$r = Run-Op 'pr-view' @{ number=1 } @{ MOCK_HTTP_FAIL='404' }
Write-Output ("F3_404: error={0}" -f $r.res.error_category)
Write-Output ("  PASS=" + ($r.res.error_category -eq 'GITHUB_4XX'))

# F3/F4: 500 -> GITHUB_5XX, state FAILED (no false SUCCEEDED)
$r = Run-Op 'pr-view' @{ number=1 } @{ MOCK_HTTP_FAIL='500' }
Write-Output ("F3_500: error={0} state={1}" -f $r.res.error_category, $r.res.state)
Write-Output ("  PASS=" + (($r.res.error_category -eq 'GITHUB_5XX') -and ($r.res.state -eq 'FAILED')))

Write-Output "F1F5_TEST_DONE"
