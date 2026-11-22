# Result-size boundary (exact) + duplicate result-key cases (isolated wrapper path).
$ErrorActionPreference = 'Continue'
$adapter = 'D:\AI\ASES-DeepSeek\enforcement\adapters\ases-agent'
$wrapper = Join-Path $adapter 'wrapper.ps1'
$enc = New-Object System.Text.UTF8Encoding($false)

function Get-Sha256Hex([byte[]]$B) { $s=[System.Security.Cryptography.SHA256]::Create(); try { ([BitConverter]::ToString($s.ComputeHash($B)) -replace '-','').ToLower() } finally { $s.Dispose() } }
function ConvertTo-CanonicalJson([object]$V) {
    if ($null -eq $V) { return 'null' }
    if ($V -is [bool]) { return $(if($V){'true'}else{'false'}) }
    if ($V -is [string]) { $sb=New-Object System.Text.StringBuilder; [void]$sb.Append('"'); foreach($ch in $V.ToCharArray()){ switch($ch){ '"'{[void]$sb.Append('\"')} '\'{[void]$sb.Append('\\')} "`b"{[void]$sb.Append('\b')} "`f"{[void]$sb.Append('\f')} "`n"{[void]$sb.Append('\n')} "`r"{[void]$sb.Append('\r')} "`t"{[void]$sb.Append('\t')} default{ if([int]$ch -lt 0x20){[void]$sb.Append('\u'+([int]$ch).ToString('x4'))}else{[void]$sb.Append($ch)} } } }; [void]$sb.Append('"'); return $sb.ToString() }
    if ($V -is [System.Management.Automation.PSCustomObject]) { $ht=@{}; foreach($p in $V.PSObject.Properties){$ht[$p.Name]=$p.Value}; return (ConvertTo-CanonicalJson $ht) }
    if ($V -is [System.Collections.IDictionary]) { $sb=New-Object System.Text.StringBuilder; [void]$sb.Append('{'); $f=$true; $ka=@($V.Keys|ForEach-Object{[string]$_}); [System.Array]::Sort($ka,[System.StringComparer]::Ordinal); foreach($k in $ka){ if(-not $f){[void]$sb.Append(',')}; [void]$sb.Append((ConvertTo-CanonicalJson $k)); [void]$sb.Append(':'); [void]$sb.Append((ConvertTo-CanonicalJson $V[$k])); $f=$false }; [void]$sb.Append('}'); return $sb.ToString() }
    if ($V -is [System.Collections.IEnumerable]) { $sb=New-Object System.Text.StringBuilder; [void]$sb.Append('['); $f=$true; foreach($i in $V){ if(-not $f){[void]$sb.Append(',')}; [void]$sb.Append((ConvertTo-CanonicalJson $i)); $f=$false }; [void]$sb.Append(']'); return $sb.ToString() }
    if ($V -is [double] -or $V -is [single]) { return ([string]$V).ToLowerInvariant() }
    if ($V -is [int] -or $V -is [long] -or $V -is [decimal] -or $V -is [byte]) { return [string]$V }
    return (ConvertTo-CanonicalJson ([string]$V))
}

$tr = Join-Path $env:TEMP ("ases-szr-"+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path (Join-Path $tr 'run'),(Join-Path $tr 'state\ops'),(Join-Path $tr 'config'),(Join-Path $tr 'logs')|Out-Null
[System.IO.File]::WriteAllText((Join-Path $tr '.ases-agent-test-root'),'s',$enc)
Copy-Item (Join-Path $adapter 'config\policy.json') (Join-Path $tr 'config\policy.json') -Force

# helper: launch wrapper paused, mutate result via raw JSON string replace, resume, return ledger + result bytes
$script:target = 0
$script:resultBytes = 0
function RunPaused([string]$name, [scriptblock]$MutateRaw) {
    $env:ASES_AGENT_ROOT=$tr; $env:ASES_TEST_PAT='fake-sz'; $env:ASES_TEST_PAUSE_BEFORE_RESULT_VALIDATE='1'
    $wp=Start-Process powershell.exe -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',$wrapper,'whoami','{}') -PassThru -WindowStyle Hidden
    $marker=$null
    for($i=0;$i -lt 40;$i++){ Start-Sleep -Milliseconds 500; $m=Get-ChildItem (Join-Path $tr 'run') -Filter '*.pause-before-result' -ErrorAction SilentlyContinue | Select-Object -First 1; if($m){$marker=$m;break} }
    if($marker){
        $opId=$marker.BaseName -replace '\.pause-before-result$',''
        $rp=Join-Path $tr "run\$opId.result.json"
        $c=Get-Content $rp -Raw
        $c2=& $MutateRaw $c
        [System.IO.File]::WriteAllText($rp, $c2, $enc)
        $script:resultBytes = $enc.GetByteCount($c2)
        Remove-Item -LiteralPath $marker.FullName -Force
    } else { Write-Output ("{0} MARKER_MISSING" -f $name) }
    $wp.WaitForExit(25000) | Out-Null
    $led = Get-ChildItem (Join-Path $tr 'state\ops') -Filter '*.json' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1 | ForEach-Object { Get-Content $_.FullName -Raw | ConvertFrom-Json }
    Remove-Item Env:\ASES_AGENT_ROOT -ErrorAction SilentlyContinue; Remove-Item Env:\ASES_TEST_PAT -ErrorAction SilentlyContinue; Remove-Item Env:\ASES_TEST_PAUSE_BEFORE_RESULT_VALIDATE -ErrorAction SilentlyContinue
    Write-Output ("{0} bytes={1} exit={2} state={3} note={4}" -f $name, $script:resultBytes, $wp.ExitCode, $led.state, $led.note)
}

# baseline: get result length with no pad (use raw, no mutation, but recompute hash to keep valid)
# First measure: read a normal result's byte length via a no-op pause
function RecomputeHashRaw([string]$json) {
    $o = $json | ConvertFrom-Json
    $ht=@{}; foreach($p in $o.PSObject.Properties){ if($p.Name -ne 'result_sha256'){ $ht[$p.Name]=$p.Value } }
    $nh=Get-Sha256Hex ($enc.GetBytes((ConvertTo-CanonicalJson $ht)))
    $ht['result_sha256']=$nh
    return ($ht | ConvertTo-Json -Depth 8 -Compress)
}

# measure baseline fixed length (pad=0, recomputed hash)
RunPaused 'baseline' { param($c) RecomputeHashRaw $c }
$baseLen = $script:resultBytes
Write-Output ("BASELINE_BYTES=$baseLen")

# for each target: pad scope to reach target exactly (padLen = target - baseLen)
foreach ($target in 65535, 65536, 65537) {
    $padLen = $target - $baseLen
    if ($padLen -lt 0) { $padLen = 0 }
    RunPaused "size_$target" { param($c)
        $o = $c | ConvertFrom-Json
        $o.output.scope = $o.output.scope + ('x' * $padLen)
        $ht=@{}; foreach($p in $o.PSObject.Properties){ if($p.Name -ne 'result_sha256'){ $ht[$p.Name]=$p.Value } }
        $nh=Get-Sha256Hex ($enc.GetBytes((ConvertTo-CanonicalJson $ht)))
        $ht['result_sha256']=$nh
        return ($ht | ConvertTo-Json -Depth 8 -Compress)
    }
}

# duplicate result keys (raw text injection)
RunPaused 'dup_sha' { param($c) ($c -replace '"result_sha256":', '"result_sha256":"x","result_sha256":') }
RunPaused 'dup_nested' { param($c) ($c -replace '"scope":"', '"scope":"x","scope":"') }
RunPaused 'dup_escaped' { param($c) ($c -replace '"result_sha256":', '"\u0072esult_sha256":"x","result_sha256":') }
Write-Output "FINAL_GAPS_DONE"
