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

# ---- Read + validate request ----
if (-not (Test-Path -LiteralPath $requestPath)) { exit 30 }
$requestSha = Get-FileSha256 $requestPath
$req = Get-Content -LiteralPath $requestPath -Raw | ConvertFrom-Json
if ($req.schema -ne 'ases-agent-op-request/1' -or $req.op_id -ne $OpId) { exit 31 }
if ([datetime]::Parse($req.expires_utc) -lt (Get-Date).ToUniversalTime()) { exit 32 }

$policy = Get-Content -LiteralPath $policyPath -Raw | ConvertFrom-Json

# ---- Claim via exclusive-create (FDR-2) ----
try {
    $claimStream = [System.IO.File]::Open($claimPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    $claimStream.Close()
} catch { exit 33 }   # another runner already claimed

$script:requestSha = $requestSha

# ---- PAT acquisition (interactive in production; injected in tests) ----
$securePat = $null
if ($PSBoundParameters.ContainsKey('TestPat')) {
    $securePat = ConvertTo-SecureString $TestPat -AsPlainText -Force
} else {
    # Summary to Founder
    Write-Host "=== ASES operation ===" -ForegroundColor Cyan
    Write-Host "op      : $($req.op)"
    Write-Host "op_id   : $OpId"
    Write-Host "request : SHA-256 $requestSha"
    Write-Host "Enter PAT (empty/close/Ctrl+C = cancel):" -ForegroundColor Yellow
    $securePat = Read-Host -AsSecureString
    if (-not $securePat -or $securePat.Length -eq 0) { if (Test-Path -LiteralPath $claimPath) { try { Remove-Item -LiteralPath $claimPath -Force } catch {} }; exit 40 }
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

# ---- Identity verify (§7.6) ----
$ghCmd = if ($UseMockGh) { (Join-Path $root 'mock-gh.ps1') } else { 'gh' }
$who = $null
if ($UseMockGh) {
    $who = & powershell -NoProfile -File $ghCmd 'api' 'user' 2>&1 | Out-String | ConvertFrom-Json
} else {
    $who = (& gh api user 2>&1 | Out-String | ConvertFrom-Json)
}
if ($who.login -ne $policy.identity.login) {
    Write-Result 'FAILED' 'IDENTITY_MISMATCH' $null 'OK'
    foreach ($p in @($claimPath, $intentPath)) { if (Test-Path -LiteralPath $p) { try { Remove-Item -LiteralPath $p -Force } catch {} } }
    if (Test-Path -LiteralPath $tmpCfg) { try { Remove-Item -LiteralPath $tmpCfg -Recurse -Force } catch {} }
    exit 41
}

# ---- Execute the single operation (§8) ----
$out = $null; $errCat = $null; $state = 'SUCCEEDED'
try {
    $outJson = if ($UseMockGh) {
        & powershell -NoProfile -File $ghCmd $req.op ($req.params | ConvertTo-Json -Compress) 2>&1 | Out-String
    } else {
        & gh $req.op ($req.params | ConvertTo-Json -Compress) 2>&1 | Out-String
    }
    $out = $outJson
} catch { $state = 'FAILED'; $errCat = 'GITHUB_5XX' }

# ---- Write result ----
$cleanupStatus = 'OK'
try { Remove-Item -LiteralPath $tmpCfg -Recurse -Force -ErrorAction Stop } catch { $cleanupStatus = 'FAILED' }
Write-Result $state $errCat $out $cleanupStatus

# ---- Cleanup claim + intent (keep result for wrapper) ----
foreach ($p in @($claimPath, $intentPath)) { if (Test-Path -LiteralPath $p) { try { Remove-Item -LiteralPath $p -Force } catch {} } }
exit 0
