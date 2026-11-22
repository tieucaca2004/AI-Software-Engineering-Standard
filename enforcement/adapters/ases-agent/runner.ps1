#Requires -Version 5.1
# ASES Rev3 Phase 1 — Interactive Runner. Writes claim/intent/result files only (never the ledger).
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OpId,
    # Test-only injection (NOT used in production): a PAT string and a mock gh path.
    [string]$TestPat,
    # Test-only empty-PAT injection (T03): an empty/cancelled SecureString.
    [switch]$EmptyPat,
    [switch]$UseMockGh,
    # Runtime root authorized by the wrapper (validated independently below).
    [string]$RuntimeRoot
)

$ErrorActionPreference = 'Stop'
$CodeRoot = $PSScriptRoot
$ProductionRuntime = Join-Path $env:USERPROFILE '.ases-agent'

function Resolve-RuntimeRoot([string]$Provided, [string]$Override, [string]$Production) {
    $prod = [System.IO.Path]::GetFullPath($Production).TrimEnd('\')
    $overrideActive = -not [string]::IsNullOrWhiteSpace($Override)
    if (-not $overrideActive -and [string]::IsNullOrWhiteSpace($Provided)) {
        return $prod
    }
    $target = if (-not [string]::IsNullOrWhiteSpace($Provided)) { $Provided } else { $Override }
    $canonical = [System.IO.Path]::GetFullPath($target.Trim()).TrimEnd('\')
    if ($canonical -eq $prod) {
        if ($overrideActive) { throw 'test mode cannot target the production runtime' }
        return $prod
    }
    $walk = $canonical
    while ($walk) {
        $item = Get-Item -LiteralPath $walk -Force -ErrorAction SilentlyContinue
        if (-not $item) { throw "RuntimeRoot path does not exist: $walk" }
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -eq [System.IO.FileAttributes]::ReparsePoint) {
            throw "RuntimeRoot contains a reparse point/junction/symlink: $walk"
        }
        $parent = Split-Path -Parent $walk
        if ($parent -eq $walk) { break }
        $walk = $parent
    }
    if (-not (Test-Path -LiteralPath (Join-Path $canonical '.ases-agent-test-root'))) {
        throw 'RuntimeRoot missing test-root sentinel (.ases-agent-test-root)'
    }
    foreach ($sub in @('run','state','config','logs')) {
        if (-not (Test-Path -LiteralPath (Join-Path $canonical $sub))) { throw "RuntimeRoot missing subdirectory: $sub" }
    }
    return $canonical
}

$resolvedRuntime = Resolve-RuntimeRoot $RuntimeRoot $env:ASES_AGENT_ROOT $ProductionRuntime
$runDir = Join-Path $resolvedRuntime 'run'
$policyPath = Join-Path $resolvedRuntime 'config\policy.json'
$requestPath = Join-Path $runDir "$OpId.request.json"
$resultPath = Join-Path $runDir "$OpId.result.json"
$claimPath = Join-Path $runDir "$OpId.claimed"
$intentPath = Join-Path $runDir "$OpId.intent"
$tmpCfg = Join-Path $runDir "$OpId.ghcfg"

function Get-UtcNow { (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ') }
function Get-FileSha256([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLower() }

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

function Test-RequestFieldTypes($obj) {
    if ($obj.schema -isnot [string] -or $obj.schema -cne 'ases-agent-op-request/1') { return 'schema must be "ases-agent-op-request/1"' }
    if ($obj.op_id -isnot [string] -or $obj.op_id -notmatch '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') { return 'op_id must be a UUID v4' }
    if ($obj.op -isnot [string]) { return 'op must be a string' }
    if ($obj.params -isnot [System.Management.Automation.PSCustomObject]) { return 'params must be an object' }
    if ($obj.created_utc -isnot [string]) { return 'created_utc must be a string' }
    if ($obj.expires_utc -isnot [string]) { return 'expires_utc must be a string' }
    if ($obj.policy_sha256 -isnot [string] -or $obj.policy_sha256 -notmatch '^[0-9a-f]{64}$') { return 'policy_sha256 must be a 64-hex string' }
    foreach ($f in @('created_utc','expires_utc')) {
        if (-not (Test-UtcTimestamp $obj.$f)) { return "$f must be ISO-8601 UTC (Z)" }
    }
    return $null
}

function Write-Result([string]$State, $ErrorCategory, $Output, [string]$CleanupStatus) {
    $base = @{
        schema = 'ases-agent-op-result/1'
        op_id = $OpId
        request_sha256 = $script:requestSha
        state = $State
        error_category = $ErrorCategory
        output = $Output
        completed_utc = Get-UtcNow
        cleanup_status = $CleanupStatus
    }
    $canonical = ConvertTo-CanonicalJson $base
    $hash = Get-Sha256Hex ([System.Text.Encoding]::UTF8.GetBytes($canonical))
    $r = $base.Clone()
    $r['result_sha256'] = $hash
    $json = $r | ConvertTo-Json -Depth 8 -Compress
    $tmp = "$resultPath.tmp"
    [System.IO.File]::WriteAllText($tmp, $json, (New-Object System.Text.UTF8Encoding($false)))
    [System.IO.File]::Move($tmp, $resultPath)
}

function Get-CleanupStatus {
    $status = 'OK'
    foreach ($p in @($claimPath, $intentPath)) { if (Test-Path -LiteralPath $p) { try { Remove-Item -LiteralPath $p -Force } catch { $status = 'FAILED' } } }
    if (Test-Path -LiteralPath $tmpCfg) { try { Remove-Item -LiteralPath $tmpCfg -Recurse -Force -ErrorAction Stop } catch { $status = 'FAILED' } }
    return $status
}

function Invoke-GhApi([string[]]$ApiArgs) {
    if ($UseMockGh) {
        $out = & powershell -NoProfile -ExecutionPolicy Bypass -File $ghCmd 'api' @ApiArgs 2>&1 | Out-String
    } else {
        $out = & gh api @ApiArgs 2>&1 | Out-String
    }
    return @{ out = $out; code = $LASTEXITCODE }
}

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

# ---- Read + validate request (strict) ----
if (-not (Test-Path -LiteralPath $requestPath)) { exit 30 }
$requestSha = Get-FileSha256 $requestPath
$req = $null
try {
    $req = Get-ValidatedJson $requestPath @('schema','op_id','op','params','created_utc','expires_utc','policy_sha256') @('schema','op_id','op','params','created_utc','expires_utc','policy_sha256')
} catch { exit 31 }
if (Test-RequestFieldTypes $req) { exit 31 }
if ($req.op_id -cne $OpId) { exit 31 }
try { if ([datetime]::Parse($req.expires_utc) -lt (Get-Date).ToUniversalTime()) { exit 32 } } catch { exit 31 }

$policy = Get-Content -LiteralPath $policyPath -Raw | ConvertFrom-Json
$repo = $policy.repo

# ---- Claim via exclusive-create (FDR-2) ----
try {
    $claimStream = [System.IO.File]::Open($claimPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    $claimStream.Close()
} catch { exit 33 }

$script:requestSha = $requestSha

# ---- PAT acquisition ----
$securePat = $null
if ($EmptyPat) {
    $securePat = $null  # test-only empty/cancelled PAT -> AUTH_MISSING (T03)
} elseif ($PSBoundParameters.ContainsKey('TestPat')) {
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
    Write-Result 'CANCELED' 'AUTH_MISSING' $null (Get-CleanupStatus)
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
$fs.Flush($true); $fs.Close()

# ---- Identity verify (§7.6) ----
$ghCmd = if ($UseMockGh) { (Join-Path $CodeRoot 'mock-gh.ps1') } else { 'gh' }
if ($UseMockGh) {
    $idOut = & powershell -NoProfile -ExecutionPolicy Bypass -File $ghCmd 'api' 'user' 2>&1 | Out-String
} else {
    $idOut = & gh api user --include 2>&1 | Out-String
}
$idCode = $LASTEXITCODE
if ($idCode -ne 0) {
    $idErr = Classify-GhError $idCode $idOut
    Write-Result 'FAILED' $idErr $null (Get-CleanupStatus)
    exit 42
}
$id = Parse-GhInclude $idOut
if ($id.scope -and $id.scope -ne 'repo') {
    Write-Result 'FAILED' 'SCOPE_MISMATCH' $null (Get-CleanupStatus)
    exit 43
}
if ($id.login -ne $policy.identity.login) {
    Write-Result 'FAILED' 'IDENTITY_MISMATCH' $null (Get-CleanupStatus)
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

# ---- Execute the single operation (§8) ----
$state = 'SUCCEEDED'; $errCat = $null; $out = $null

switch ($req.op) {
    'whoami' {
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

# ---- Write result (with result_sha256 + propagated cleanup status) ----
Write-Result $state $errCat $out (Get-CleanupStatus)
exit 0
