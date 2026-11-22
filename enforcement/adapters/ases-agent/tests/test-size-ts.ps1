# Size-boundary + timestamp validation (isolated, direct runner for request; wrapper for result).
$ErrorActionPreference = 'Continue'
$adapter = 'D:\AI\ASES-DeepSeek\enforcement\adapters\ases-agent'
$runner = Join-Path $adapter 'runner.ps1'
$wrapper = Join-Path $adapter 'wrapper.ps1'

function New-Root { $tr=Join-Path $env:TEMP ("ases-sz-"+[guid]::NewGuid().ToString('N')); New-Item -ItemType Directory -Force -Path (Join-Path $tr 'run'),(Join-Path $tr 'state\ops'),(Join-Path $tr 'config'),(Join-Path $tr 'logs')|Out-Null; [System.IO.File]::WriteAllText((Join-Path $tr '.ases-agent-test-root'),'s',(New-Object System.Text.UTF8Encoding($false))); Copy-Item (Join-Path $adapter 'config\policy.json') (Join-Path $tr 'config\policy.json') -Force; return $tr }
$tr = New-Root
$enc = New-Object System.Text.UTF8Encoding($false)
$now=(Get-Date).ToUniversalTime().ToString('o'); $exp=(Get-Date).ToUniversalTime().AddMinutes(10).ToString('o')

function Build-Request([string]$id, [int]$targetBytes) {
    $tmpl = '{"schema":"ases-agent-op-request/1","op_id":"' + $id + '","op":"whoami","params":{"pad":"{PAD}"},"created_utc":"' + $now + '","expires_utc":"' + $exp + '","policy_sha256":"' + ('a'*64) + '"}'
    $base = $enc.GetByteCount($tmpl.Replace('{PAD}',''))
    $padLen = $targetBytes - $base
    if ($padLen -lt 0) { $padLen = 0 }
    $s = $tmpl.Replace('{PAD}', ('x' * $padLen))
    return $enc.GetBytes($s)
}
function Run-Request([byte[]]$b, [string]$id) {
    [System.IO.File]::WriteAllBytes((Join-Path $tr "run\$id.request.json"), $b)
    $out = & powershell -NoProfile -ExecutionPolicy Bypass -File $runner -OpId $id -TestPat fake -UseMockGh -RuntimeRoot $tr 2>&1 | Out-String
    return $LASTEXITCODE
}

foreach ($sz in 65535, 65536, 65537) {
    $id=[guid]::NewGuid().ToString()
    $b = Build-Request $id $sz
    $code = Run-Request $b $id
    Write-Output ("SIZE_REQ_{0} actual=$($b.Length) exit=$code" -f $sz)
}

# timestamp validation
function Run-Ts([string]$tsField, [string]$tsValue) {
    $id=[guid]::NewGuid().ToString()
    $body = '{"schema":"ases-agent-op-request/1","op_id":"' + $id + '","op":"whoami","params":{},"created_utc":"' + $now + '","expires_utc":"' + $exp + '","policy_sha256":"' + ('a'*64) + '"}'
    $body = $body.Replace($tsField, $tsValue)
    $b = $enc.GetBytes($body)
    [System.IO.File]::WriteAllBytes((Join-Path $tr "run\$id.request.json"), $b)
    $out = & powershell -NoProfile -ExecutionPolicy Bypass -File $runner -OpId $id -TestPat fake -UseMockGh -RuntimeRoot $tr 2>&1 | Out-String
    return $LASTEXITCODE
}
# valid UTC (baseline)
Write-Output ("TS_valid exit=" + (Run-Ts '"created_utc":"' + $now + '"' '"created_utc":"' + $now + '"'))
# non-UTC offset (+07:00)
Write-Output ("TS_nonutc_offset exit=" + (Run-Ts '"created_utc":"' + $now + '"' '"created_utc":"2026-11-22T10:00:00+07:00"'))
# missing timezone (no Z, no offset)
Write-Output ("TS_missing_tz exit=" + (Run-Ts '"created_utc":"' + $now + '"' '"created_utc":"2026-11-22T10:00:00"'))
# invalid calendar date (month 13)
Write-Output ("TS_invalid_date exit=" + (Run-Ts '"created_utc":"' + $now + '"' '"created_utc":"2026-13-40T10:00:00Z"'))
# malformed (garbage)
Write-Output ("TS_malformed exit=" + (Run-Ts '"created_utc":"' + $now + '"' '"created_utc":"not-a-date"'))
Write-Output "SIZE_TS_DONE"
