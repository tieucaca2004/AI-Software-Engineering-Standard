# Result-integrity tests (psobject cases, inline pause+tamper).
$ErrorActionPreference = 'Continue'
$adapter = 'D:\AI\ASES-DeepSeek\enforcement\adapters\ases-agent'
$wrapper = Join-Path $adapter 'wrapper.ps1'

$tr = Join-Path $env:TEMP ("ases-ri4-"+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path (Join-Path $tr 'run'),(Join-Path $tr 'state\ops'),(Join-Path $tr 'config'),(Join-Path $tr 'logs')|Out-Null
[System.IO.File]::WriteAllText((Join-Path $tr '.ases-agent-test-root'),'s',(New-Object System.Text.UTF8Encoding($false)))
Copy-Item (Join-Path $adapter 'config\policy.json') (Join-Path $tr 'config\policy.json') -Force

$cases = @(
    [pscustomobject]@{Name='modified_preserved_hash'; Pat='"login":"chautinhtinh3979"'; Rep='"login":"evil"'},
    [pscustomobject]@{Name='wrong_hash'; Pat='"result_sha256":"[0-9a-f]{64}"'; Rep=('"result_sha256":"' + ('f'*64) + '"')},
    [pscustomobject]@{Name='empty_hash'; Pat='"result_sha256":"[0-9a-f]{64}"'; Rep='"result_sha256":""'},
    [pscustomobject]@{Name='short_hash'; Pat='"result_sha256":"[0-9a-f]{64}"'; Rep='"result_sha256":"abc"'},
    [pscustomobject]@{Name='nonhex_hash'; Pat='"result_sha256":"[0-9a-f]{64}"'; Rep=('"result_sha256":"' + ('z'*64) + '"')},
    [pscustomobject]@{Name='long_hash'; Pat='"result_sha256":"[0-9a-f]{64}"'; Rep=('"result_sha256":"' + ('a'*65) + '"')}
)

foreach ($case in $cases) {
    $env:ASES_AGENT_ROOT=$tr; $env:ASES_TEST_PAT='fake-ri'; $env:ASES_TEST_PAUSE_BEFORE_RESULT_VALIDATE='1'
    $wp=Start-Process powershell.exe -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',$wrapper,'whoami','{}') -PassThru -WindowStyle Hidden
    $marker=$null
    for($i=0;$i -lt 40;$i++){
        Start-Sleep -Milliseconds 500
        $m=Get-ChildItem (Join-Path $tr 'run') -Filter '*.pause-before-result' -ErrorAction SilentlyContinue | Select-Object -First 1
        if($m){ $marker=$m; break }
    }
    if($marker){
        $opId=$marker.BaseName -replace '\.pause-before-result$',''
        $rp=Join-Path $tr "run\$opId.result.json"
        $c=Get-Content $rp -Raw
        $c2=$c -replace $case.Pat, $case.Rep
        [System.IO.File]::WriteAllText($rp, $c2, (New-Object System.Text.UTF8Encoding($false)))
        Remove-Item -LiteralPath $marker.FullName -Force
    } else {
        Write-Output ("RI_{0} MARKER_MISSING" -f $case.Name)
    }
    $wp.WaitForExit(25000) | Out-Null
    $led = Get-ChildItem (Join-Path $tr 'state\ops') -Filter '*.json' -ErrorAction SilentlyContinue | ForEach-Object { Get-Content $_.FullName -Raw | ConvertFrom-Json } | Select-Object -Last 1
    Remove-Item Env:\ASES_AGENT_ROOT -ErrorAction SilentlyContinue
    Remove-Item Env:\ASES_TEST_PAT -ErrorAction SilentlyContinue
    Remove-Item Env:\ASES_TEST_PAUSE_BEFORE_RESULT_VALIDATE -ErrorAction SilentlyContinue
    Write-Output ("RI_{0} exit={1} state={2} note={3}" -f $case.Name, $wp.ExitCode, $led.state, $led.note)
}
Write-Output "RESULT_INTEGRITY_DONE"
