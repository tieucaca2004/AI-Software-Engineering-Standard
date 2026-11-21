# Mock gh for isolated Phase 1 verification (NO real GitHub, NO real token).
param([string]$Sub = '', [string]$Arg2 = '', [string]$Arg3 = '')

# Test-only fault-injection hook (not used in production): delay to widen a kill window.
if ($env:MOCK_SLEEP_SECONDS) { Start-Sleep -Seconds ([int]$env:MOCK_SLEEP_SECONDS) }

$login = if ($env:MOCK_LOGIN) { $env:MOCK_LOGIN } else { 'chautinhtinh3979' }
$scope = if ($env:MOCK_SCOPE) { $env:MOCK_SCOPE } else { 'repo' }
$expiry = if ($env:MOCK_TOKEN_EXPIRY) { $env:MOCK_TOKEN_EXPIRY } else { '' }

if ($Sub -eq 'api') {
    $endpoint = $Arg2

    if ($env:MOCK_AUTH_FAIL -eq '401') { Write-Output 'gh: Bad credentials (HTTP 401)'; exit 1 }
    if ($env:MOCK_NETWORK_FAIL -eq '1') { Write-Output 'gh: could not connect to api.github.com:443 (connection refused)'; exit 1 }
    if ($env:MOCK_HTTP_FAIL) { Write-Output ("gh: error (HTTP " + $env:MOCK_HTTP_FAIL + ")"); exit 1 }

    # identity endpoint: return headers (scope, expiry) + JSON body (login)
    if ($endpoint -eq 'user') {
        Write-Output ("x-oauth-scopes: " + $scope)
        if ($expiry) { Write-Output ("github-authentication-token-expiration: " + $expiry) }
        Write-Output ''
        Write-Output ('{"login":"' + $login + '"}')
        exit 0
    }

    if ($endpoint -match 'collaborators/.*/permission$') {
        Write-Output '{"permission":"write","user":{"login":"chautinhtinh3979"}}'
        exit 0
    }

    if ($endpoint -match '/pulls\?') {
        Write-Output '[{"number":1,"state":"OPEN","head":{"ref":"feat/x"},"base":{"ref":"main"}}]'
        exit 0
    }

    if ($endpoint -match '/pulls/\d+$') {
        Write-Output '{"number":1,"state":"OPEN","title":"mock","head":{"sha":"0123456789abcdef0123456789abcdef01234567"},"base":{"ref":"main"}}'
        exit 0
    }

    if ($endpoint -match '/commits/[0-9a-f]+/check-runs$') {
        Write-Output '{"check_runs":[{"name":"ases","status":"completed","conclusion":"success"}]}'
        exit 0
    }

    if ($endpoint -match '^repos/[^/]+/[^/]+$') {
        # plain repo path: GET /repos/{owner}/{repo}
        Write-Output '{"full_name":"tieucaca2004/AI-Software-Engineering-Standard","private":false}'
        exit 0
    }

    Write-Output '{}'
    exit 0
}

# legacy direct-op dispatch (kept for backward test compatibility)
switch ($Sub) {
    'whoami'           { Write-Output ('{"login":"' + $login + '"}') }
    'repo-permissions' { Write-Output '{"permission":"write","user":{"login":"chautinhtinh3979"}}' }
    'pr-list'          { Write-Output '[{"number":1,"state":"OPEN","head":{"ref":"feat/x"}}]' }
    'pr-view'          { Write-Output '{"number":1,"state":"OPEN","title":"mock"}' }
    'pr-checks'        { Write-Output '{"check_runs":[{"name":"ases","status":"completed","conclusion":"success"}]}' }
    'pr-create'        { Write-Output '{"number":99,"html_url":"https://example.invalid/99"}' }
    'expiry'           { if ($expiry) { Write-Output $expiry } else { Write-Output '' } }
    default            { Write-Output '{}' }
}
exit 0
