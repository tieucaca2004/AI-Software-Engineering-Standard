# Type-enforcement + strict-JSON regression (isolated, direct-runner for request; byte-level for UTF-8/size).
$ErrorActionPreference = 'Continue'
$adapter = 'D:\AI\ASES-DeepSeek\enforcement\adapters\ases-agent'
$runner = Join-Path $adapter 'runner.ps1'

function New-Root {
    $tr = Join-Path $env:TEMP ("ases-type-" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path (Join-Path $tr 'run'), (Join-Path $tr 'state\ops'), (Join-Path $tr 'config'), (Join-Path $tr 'logs') | Out-Null
    [System.IO.File]::WriteAllText((Join-Path $tr '.ases-agent-test-root'), 's', (New-Object System.Text.UTF8Encoding($false)))
    Copy-Item (Join-Path $adapter 'config\policy.json') (Join-Path $tr 'config\policy.json') -Force
    return $tr
}
$tr = New-Root
function Run-Req([string]$opId, [byte[]]$bytes) {
    [System.IO.File]::WriteAllBytes((Join-Path $tr "run\$opId.request.json"), $bytes)
    $out = & powershell -NoProfile -ExecutionPolicy Bypass -File $runner -OpId $opId -TestPat fake -UseMockGh -RuntimeRoot $tr 2>&1 | Out-String
    return $LASTEXITCODE
}
$enc = New-Object System.Text.UTF8Encoding($false)
$now = (Get-Date).ToUniversalTime().ToString('o'); $exp = (Get-Date).ToUniversalTime().AddMinutes(10).ToString('o')
function Mk([string]$body) {
    # body already includes schema/op_id/op/params/created_utc/expires_utc/policy_sha256 with placeholders replaced below
    return $enc.GetBytes($body)
}
$validBody = '{"schema":"ases-agent-op-request/1","op_id":"{ID}","op":"whoami","params":{},"created_utc":"{NOW}","expires_utc":"{EXP}","policy_sha256":"' + ('a'*64) + '"}'
$id = [guid]::NewGuid().ToString()
# valid
Write-Output ("TYPE_valid exit=" + (Run-Req $id (Mk ($validBody.Replace('{ID}',$id).Replace('{NOW}',$now).Replace('{EXP}',$exp)))))

# wrong types
$cases = @(
    @{ n='op_number'; b=$validBody.Replace('"op":"whoami"','"op":123') },
    @{ n='params_array'; b=$validBody.Replace('"params":{}','"params":[]') },
    @{ n='params_string'; b=$validBody.Replace('"params":{}','"params":"x"') },
    @{ n='opid_bad_uuid'; b=$validBody.Replace('{ID}','not-a-uuid') },
    @{ n='policy_short'; b=$validBody.Replace('"policy_sha256":"' + ('a'*64) + '"','"policy_sha256":"abc"') },
    @{ n='created_number'; b=$validBody.Replace('"created_utc":"{NOW}"','"created_utc":123') },
    @{ n='expires_bool'; b=$validBody.Replace('"expires_utc":"{EXP}"','"expires_utc":true') },
    @{ n='schema_wrong'; b=$validBody.Replace('"schema":"ases-agent-op-request/1"','"schema":"x"') }
)
foreach ($c in $cases) {
    $cid = [guid]::NewGuid().ToString()
    $body = $c.b.Replace('{ID}',$cid).Replace('{NOW}',$now).Replace('{EXP}',$exp)
    Write-Output ("TYPE_{0} exit={1}" -f $c.n, (Run-Req $cid (Mk $body)))
}

# duplicate nested key (params with dup)
$dupNested = $validBody.Replace('{ID}',[guid]::NewGuid().ToString()).Replace('{NOW}',$now).Replace('{EXP}',$exp).Replace('"params":{}','"params":{"a":1,"a":2}')
$did=[guid]::NewGuid().ToString()
Write-Output ("DUP_nested exit=" + (Run-Req $did (Mk ($dupNested.Replace('{ID}',$did)))))

# duplicate escaped-equivalent key
$escDup = '{"schema":"ases-agent-op-request/1","op_id":"{ID}","op":"whoami","\u006fp":"whoami","params":{},"created_utc":"{NOW}","expires_utc":"{EXP}","policy_sha256":"' + ('a'*64) + '"}'
$eid=[guid]::NewGuid().ToString()
Write-Output ("DUP_escaped exit=" + (Run-Req $eid (Mk ($escDup.Replace('{ID}',$eid).Replace('{NOW}',$now).Replace('{EXP}',$exp)))))

# UTF-8: BOM, invalid byte (0xFF), truncated multibyte (0xC3)
$okBody = $validBody.Replace('{ID}',[guid]::NewGuid().ToString()).Replace('{NOW}',$now).Replace('{EXP}',$exp)
$bid=[guid]::NewGuid().ToString()
$bom = [byte[]](0xEF,0xBB,0xBF) + (Mk ($okBody.Replace('{ID}',$bid)))
Write-Output ("UTF8_bom exit=" + (Run-Req $bid $bom))
$iid=[guid]::NewGuid().ToString()
$inv = (Mk ($okBody.Replace('{ID}',$iid))) + [byte]0xFF
Write-Output ("UTF8_invalid_byte exit=" + (Run-Req $iid $inv))
$tid=[guid]::NewGuid().ToString()
$trunc = (Mk ($okBody.Replace('{ID}',$tid))) + [byte]0xC3
Write-Output ("UTF8_truncated exit=" + (Run-Req $tid $trunc))

# size boundary: 65537 bytes (over limit) — pad params
$target = 65537
$baseNoParams = '{"schema":"ases-agent-op-request/1","op_id":"{ID}","op":"whoami","params":{"pad":"{PAD}"},"created_utc":"{NOW}","expires_utc":"{EXP}","policy_sha256":"' + ('a'*64) + '"}'
$sid=[guid]::NewGuid().ToString()
# compute pad length so total == target
$overhead = $enc.GetByteCount($baseNoParams.Replace('{ID}',$sid).Replace('{NOW}',$now).Replace('{EXP}',$exp).Replace('{PAD}',''))
$padLen = $target - $overhead
if ($padLen -lt 0) { $padLen = 0 }
$padStr = 'x' * $padLen
$big = $baseNoParams.Replace('{ID}',$sid).Replace('{NOW}',$now).Replace('{EXP}',$exp).Replace('{PAD}',$padStr)
$bigBytes = $enc.GetBytes($big)
Write-Output ("SIZE_65537 actual_bytes=$($bigBytes.Length) exit=" + (Run-Req $sid $bigBytes))

Write-Output "TYPE_ENFORCE_DONE"
