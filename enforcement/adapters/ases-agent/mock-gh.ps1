# Mock gh for isolated Phase 1 verification (NO real GitHub, NO real token).
param([string]$Sub = '', [string]$Arg2 = '', [string]$Arg3 = '')

# Test-only fault-injection hook (not used in production): delay to widen a kill window.
if ($env:MOCK_SLEEP_SECONDS) { Start-Sleep -Seconds ([int]$env:MOCK_SLEEP_SECONDS) }

$login = if ($env:MOCK_LOGIN) { $env:MOCK_LOGIN } else { 'chautinhtinh3979' }

if ($Sub -eq 'api' -and $Arg2 -eq 'user') {
    Write-Output ('{"login":"' + $login + '"}')
    exit 0
}

switch ($Sub) {
    'whoami'           { Write-Output ('{"login":"' + $login + '"}') }
    'repo-permissions' { Write-Output '{"permission":"write","user":{"login":"chautinhtinh3979"}}' }
    'pr-list'          { Write-Output '[{"number":1,"state":"OPEN","head":{"ref":"feat/x"}}]' }
    'pr-view'          { Write-Output '{"number":1,"state":"OPEN","title":"mock"}' }
    'pr-checks'        { Write-Output '{"check_runs":[{"name":"ases","status":"completed","conclusion":"success"}]}' }
    'pr-create'        { Write-Output '{"number":99,"html_url":"https://example.invalid/99"}' }
    default            { Write-Output '{}' }
}
exit 0
