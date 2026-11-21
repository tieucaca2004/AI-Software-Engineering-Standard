#Requires -Version 5.1
# ASES Rev3 Phase 1 — Interactive Runner. Writes claim/intent/result files only (never the ledger).
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OpId,
    # Test-only injection (NOT used in production): a PAT string and a mock gh path.
    [string]$TestPat,
    [switch]$UseMockGh
)

$ErrorActionPreference = 'Stop'
$root = Join-Path $env:USERPROFILE '.ases-agent'
$runDir = Join-Path $root 'run'
$policyPath = Join-Path $root 'config\policy.json'
$requestPath = Join-Path $runDir "$OpId.request.json"
$resultPath = Join-Path $runDir "$OpId.result.json"
$claimPath = Join-Path $runDir "$OpId.claimed"
$intentPath = Join-Path $runDir "$OpId.intent"

function Get-UtcNow { (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ') }
function Get-FileSha256([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLower() }

function Write-Result([string]$State, $ErrorCategory, $Output, [string]$CleanupStatus) {
    $r = @{
        schema = 'ases-agent-op-result/1'
        op_id = $OpId
        request_sha256 = $script:requestSha
        state = $State
        error_category = $ErrorCategory
        output = $Output
        completed_utc = Get-UtcNow
        cleanup_status = $CleanupStatus
    }
    $json = $r | ConvertTo-Json -Depth 8 -Compress
    $tmp = "$resultPath.tmp"
    [System.IO.File]::WriteAllText($tmp, $json, (New-Object System.Text.UTF8Encoding($false)))
    [System.IO.File]::Move($tmp, $resultPath)
}

function Cleanup-RunnerFiles {
    foreach ($p in @($claimPath, $intentPath)) { if (Test-Path -LiteralPath $p) { try { Remove-Item -LiteralPath $p -Force } catch {} } }
    if (Test-Path -LiteralPath $tmpCfg) { try { Remove-Item -LiteralPath $tmpCfg -Recurse -Force } catch {} }
}

# Run a gh api call; returns @{ out; code }.
function Invoke-GhApi([string[]]$ApiArgs) {
    if ($UseMockGh) {
        $out = & powershell -NoProfile -ExecutionPolicy Bypass -File $ghCmd 'api' @ApiArgs 2>&1 | Out-String
    } else {
        $out = & gh api @ApiArgs 2>&1 | Out-String
    }
    return @{ out = $out; code = $LASTEXITCODE }
}

# Classify a gh failure into an ASES error category (§§8-9).
function Classify-GhError([int]$Code, [string]$Out) {
    if ($Out -match '\(HTTP\s+(\d{3})\)') {
        $status = [int]$Matches[1]
        if ($status -eq 401) { return 'AUTH_INVALID' }
        if ($status -ge 400 -and $status -lt 500) { return 'GITHUB_4XX' }
        if ($status -ge 500) { return 'GITHUB_5XX' }
    }
    if ($Out -match 'could not connect|connection refused|timed out|resolve host|network|unreachable') { return 'NETWORK' }
    return 'GITHUB_5XX'
}

# Parse `gh api --include` output (headers + JSON body). Returns @{ login; scope; expiry }.
function Parse-GhInclude([string]$Text) {
    $r = @{ login = ''; scope = ''; expiry = '' }
    $lines = $Text -split "`r?`n"
    $bodyStart = -1
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i].Trim() -eq '') { $bodyStart = $i; break }
        if ($lines[$i] -match 'x-oauth-scopes\s*:\s*(.+)') { $r.scope = $Matches[1].Trim() }
        if ($lines[$i] -match 'token-expiration\s*:\s*(.+)') { $r.expiry = $Matches[1].Trim() }
    }
    if ($bodyStart -ge 0 -and ($bodyStart + 1) -lt $lines.Count) {
        $body = (($lines[($bodyStart + 1)..($lines.Count - 1)]) -join "`n").Trim()
        try { $j = $body | ConvertFrom-Json; $r.login = [string]$j.login } catch {}
    }
    return $r
}

# ---- Read + validate request ----
if (-not (Test-Path -LiteralPath $requestPath)) { exit 30 }
$requestSha = Get-FileSha256 $requestPath
$req = Get-Content -LiteralPath $requestPath -Raw | ConvertFrom-Json
if ($req.schema -ne 'ases-agent-op-request/1' -or $req.op_id -ne $OpId) { exit 31 }
if ([datetime]::Parse($req.expires_utc) -lt (Get-Date).ToUniversalTime()) { exit 32 }

$policy = Get-Content -LiteralPath $policyPath -Raw | ConvertFrom-Json
$repo = $policy.repo

# ---- Claim via exclusive-create (FDR-2) ----
try {
    $claimStream = [System.IO.File]::Open($claimPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    $claimStream.Close()
} catch { exit 33 }   # another runner already claimed

$script:requestSha = $requestSha

# ---- PAT acquisition ----
$securePat = $null
if ($PSBoundParameters.ContainsKey('TestPat')) {
    $securePat = ConvertTo-SecureString $TestPat -AsPlainText -Force
} else {
    Write-Host "=== ASES operation ===" -ForegroundColor Cyan
    Write-Host "op      : $($req.op)"
    Write-Host "op_id   : $OpId"
    Write-Host "request : SHA-256 $requestSha"
    Write-Host "Enter PAT (empty/close/Ctrl+C = cancel):" -ForegroundColor Yellow
    $securePat = Read-Host -AsSecureString
}
if (-not $securePat -or $securePat.Length -eq 0) {
    Write-Result 'CANCELED' 'AUTH_MISSING' $null 'OK'
    if (Test-Path -LiteralPath $claimPath) { try { Remove-Item -LiteralPath $claimPath -Force } catch {} }
    exit 40
}
$bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePat)
try { $pat = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) } finally { [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }

# ---- Temp gh config, env for child processes only ----
$tmpCfg = Join-Path $runDir "$OpId.ghcfg"
New-Item -ItemType Directory -Force -Path $tmpCfg | Out-Null
$env:GH_TOKEN = $pat
$env:GH_CONFIG_DIR = $tmpCfg
$env:GH_PROMPT_DISABLED = '1'
$env:GH_NO_UPDATE_NOTIFIER = '1'

# ---- Durable execution-intent marker (FDR-12) BEFORE external write ----
$intentTmp = "$intentPath.tmp"
[System.IO.File]::WriteAllText($intentTmp, (Get-UtcNow), (New-Object System.Text.UTF8Encoding($false)))
[System.IO.File]::Move($intentTmp, $intentPath)
$fs = [System.IO.File]::Open($intentPath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Write, [System.IO.FileShare]::Read)
$fs.Flush($true); $fs.Close()   # FlushFileBuffers

# ---- Identity verify (§7.6): GET /user (headers + body) -> login, scope, expiry ----
$ghCmd = if ($UseMockGh) { (Join-Path $root 'mock-gh.ps1') } else { 'gh' }
if ($UseMockGh) {
    $idOut = & powershell -NoProfile -ExecutionPolicy Bypass -File $ghCmd 'api' 'user' 2>&1 | Out-String
} else {
    $idOut = & gh api user --include 2>&1 | Out-String
}
$idCode = $LASTEXITCODE
if ($idCode -ne 0) {
    $idErr = Classify-GhError $idCode $idOut
    Write-Result 'FAILED' $idErr $null 'OK'
    Cleanup-RunnerFiles
    exit 42
}
$id = Parse-GhInclude $idOut

# scope check (UQ17): X-Oauth-Scopes must equal 'repo'
if ($id.scope -and $id.scope -ne 'repo') {
    Write-Result 'FAILED' 'SCOPE_MISMATCH' $null 'OK'
    Cleanup-RunnerFiles
    exit 43
}

# login check (A4)
if ($id.login -ne $policy.identity.login) {
    Write-Result 'FAILED' 'IDENTITY_MISMATCH' $null 'OK'
    Cleanup-RunnerFiles
    exit 41
}

# ---- Token expiry (T21 / §7.6) ----
$tokenDays = $null
$tokenWarning = $false
if ($id.expiry) {
    try {
        $expDt = [datetime]::Parse($id.expiry).ToUniversalTime()
        $tokenDays = [int][math]::Floor(($expDt - (Get-Date).ToUniversalTime()).TotalDays)
        if ($tokenDays -le 14) { $tokenWarning = $true }
    } catch { $tokenDays = $null }
}
if ($tokenWarning) {
    Write-Output ("WARNING: token expires in {0} days ({1})" -f $tokenDays, $id.expiry)
} elseif (-not $id.expiry) {
    Write-Output 'WARNING: token expiry metadata unavailable'
}

# ---- Execute the single operation (§8): endpoint mapping + exit-code validation ----
$state = 'SUCCEEDED'; $errCat = $null; $out = $null

switch ($req.op) {
    'whoami' {
        # whoami output schema (§8.2): login, expiry, days-left, warning flag, scope
        $out = @{
            login = $id.login
            token_expiry_utc = $id.expiry
            token_days_left = $tokenDays
            token_expiry_warning = $tokenWarning
            scope = $id.scope
        }
    }
    'repo-permissions' {
        $r0 = Invoke-GhApi @("repos/$repo")
        if ($r0.code -ne 0) { $state = 'FAILED'; $errCat = Classify-GhError $r0.code $r0.out }
        else {
            $r1 = Invoke-GhApi @("repos/$repo/collaborators/$($policy.identity.login)/permission")
            if ($r1.code -ne 0) { $state = 'FAILED'; $errCat = Classify-GhError $r1.code $r1.out }
            else { try { $out = $r1.out | ConvertFrom-Json } catch { $state = 'FAILED'; $errCat = 'VALIDATION' } }
        }
    }
    'pr-list' {
        $ep = "repos/$repo/pulls?state=$($req.params.state)&per_page=$($req.params.limit)"
        $r1 = Invoke-GhApi @($ep)
        if ($r1.code -ne 0) { $state = 'FAILED'; $errCat = Classify-GhError $r1.code $r1.out }
        else { try { $out = $r1.out | ConvertFrom-Json } catch { $state = 'FAILED'; $errCat = 'VALIDATION' } }
    }
    'pr-view' {
        $ep = "repos/$repo/pulls/$($req.params.number)"
        $r1 = Invoke-GhApi @($ep)
        if ($r1.code -ne 0) { $state = 'FAILED'; $errCat = Classify-GhError $r1.code $r1.out }
        else { try { $out = $r1.out | ConvertFrom-Json } catch { $state = 'FAILED'; $errCat = 'VALIDATION' } }
    }
    'pr-checks' {
        $r1 = Invoke-GhApi @("repos/$repo/pulls/$($req.params.number)")
        if ($r1.code -ne 0) { $state = 'FAILED'; $errCat = Classify-GhError $r1.code $r1.out }
        else {
            try { $pr = $r1.out | ConvertFrom-Json; $headSha = $pr.head.sha } catch { $state = 'FAILED'; $errCat = 'VALIDATION' }
            if ($state -eq 'SUCCEEDED') {
                $r2 = Invoke-GhApi @("repos/$repo/commits/$headSha/check-runs")
                if ($r2.code -ne 0) { $state = 'FAILED'; $errCat = Classify-GhError $r2.code $r2.out }
                else { try { $out = $r2.out | ConvertFrom-Json } catch { $state = 'FAILED'; $errCat = 'VALIDATION' } }
            }
        }
    }
    default { $state = 'FAILED'; $errCat = 'POLICY_DENIED' }
}

# ---- Write result ----
$cleanupStatus = 'OK'
if (Test-Path -LiteralPath $tmpCfg) { try { Remove-Item -LiteralPath $tmpCfg -Recurse -Force -ErrorAction Stop } catch { $cleanupStatus = 'FAILED' } }
Write-Result $state $errCat $out $cleanupStatus

# ---- Cleanup claim + intent (keep result for wrapper) ----
foreach ($p in @($claimPath, $intentPath)) { if (Test-Path -LiteralPath $p) { try { Remove-Item -LiteralPath $p -Force } catch {} } }
exit 0
