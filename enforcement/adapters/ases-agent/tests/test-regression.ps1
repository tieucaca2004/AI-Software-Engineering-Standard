# Targeted regression for the 3 cleanup fixes. Uses NEW op_ids; never touches pre-existing residual artifacts.
$ErrorActionPreference = 'Continue'
$root = $env:ASES_AGENT_ROOT
if (-not $root) { Write-Output 'REFUSE: ASES_AGENT_ROOT not set; legacy tests require an isolated test root (never production)'; exit 90 }
if (-not (Test-Path -LiteralPath (Join-Path $root '.ases-agent-test-root'))) { Write-Output 'REFUSE: isolated test-root sentinel (.ases-agent-test-root) missing'; exit 90 }
$wrapper = Join-Path $root 'wrapper.ps1'
$runDir = Join-Path $root 'run'
$opsDir = Join-Path $root 'state\ops'

# 1. Snapshot pre-existing residual files (hash) — must NOT change.
$snapshot = @{}
Get-ChildItem -Recurse -File $runDir, $opsDir -ErrorAction SilentlyContinue | ForEach-Object {
    $snapshot[$_.FullName] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
}
Write-Output ("SNAPSHOT_PREEXISTING_FILES=" + $snapshot.Count)

# 2. Happy path (Bug 1: claim/intent path cleanup) — new op_id via wrapper
$env:ASES_TEST_PAT = 'regression-pat-0001'
$before = @(Get-ChildItem -File $runDir -ErrorAction SilentlyContinue | ForEach-Object Name)
$out = & powershell -NoProfile -ExecutionPolicy Bypass -File $wrapper 'whoami' 2>&1 | Out-String
$happyCode = $LASTEXITCODE
$after = @(Get-ChildItem -File $runDir -ErrorAction SilentlyContinue | ForEach-Object Name)
$newResidual = @($after | Where-Object { $_ -notin $before })
Write-Output ("HAPPY exit=$happyCode new_residual_files=$($newResidual -join ',')")
Write-Output ("HAPPY succeeded=$($happyCode -eq 0 -and $out -match 'SUCCEEDED')")

# 3. Identity mismatch (Bug 3b: claim/intent/tmpCfg cleanup)
$env:MOCK_LOGIN = 'wrong-login-xyz'
$before2 = @(Get-ChildItem -File $runDir -ErrorAction SilentlyContinue | ForEach-Object Name)
$out2 = & powershell -NoProfile -ExecutionPolicy Bypass -File $wrapper 'whoami' 2>&1 | Out-String
$mismatchCode = $LASTEXITCODE
$after2 = @(Get-ChildItem -File $runDir -ErrorAction SilentlyContinue | ForEach-Object Name)
$newResidual2 = @($after2 | Where-Object { $_ -notin $before2 })
$tmpCfgDirs = @(Get-ChildItem -Directory $runDir -ErrorAction SilentlyContinue | ForEach-Object Name)
Write-Output ("MISMATCH exit=$mismatchCode new_residual=$($newResidual2 -join ',') tmpcfg_dirs=$($tmpCfgDirs -join ',')")
Write-Output ("MISMATCH result_has_IDENTITY_MISMATCH=$($out2 -match 'IDENTITY_MISMATCH')")

# 4. Verify pre-existing residual files UNCHANGED
$unchanged = $true
foreach ($k in $snapshot.Keys) {
    if (Test-Path -LiteralPath $k) {
        $h = (Get-FileHash -LiteralPath $k -Algorithm SHA256).Hash
        if ($h -ne $snapshot[$k]) { $unchanged = $false; Write-Output "CHANGED: $k" }
    } else {
        $unchanged = $false; Write-Output "MISSING: $k"
    }
}
Write-Output ("PREEXISTING_UNCHANGED=$unchanged")

Remove-Item Env:\ASES_TEST_PAT -ErrorAction SilentlyContinue
Remove-Item Env:\MOCK_LOGIN -ErrorAction SilentlyContinue

# Summary
Write-Output "===== REGRESSION SUMMARY ====="
Write-Output ("Bug1_happy_clean=" + ($happyCode -eq 0 -and $newResidual.Count -eq 0))
Write-Output ("Bug3b_mismatch_clean=" + ($mismatchCode -eq 0 -and $newResidual2.Count -eq 0 -and $tmpCfgDirs.Count -eq 0))
Write-Output ("Preexisting_unchanged=" + $unchanged)
