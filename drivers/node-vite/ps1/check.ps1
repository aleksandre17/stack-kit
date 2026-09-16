# Pre-flight — frontend module (parity with backend check.sh scope)
param(
    [switch]$Quiet,
    [switch]$Remote
)

. (Join-Path $PSScriptRoot "..\_init.ps1")

$errors = 0
$warnings = 0

function Test-Check {
    param([string]$Label, [scriptblock]$Test)
    if (& $Test) {
        if (-not $Quiet) { Write-Host "  [OK]   $Label" -ForegroundColor Green }
    } else {
        Write-Host "  [FAIL] $Label" -ForegroundColor Red
        $script:errors++
    }
}
function Test-Warn {
    param([string]$Label, [string]$Msg = "")
    if (-not $Quiet) { Write-Host "  [WARN] $Label $Msg" -ForegroundColor Yellow }
    $script:warnings++
}

Write-Host ""
Write-Host "  Pre-flight (frontend)" -ForegroundColor Cyan
Write-Host ""

Test-Check "docker CLI" { (Get-Command docker -ErrorAction SilentlyContinue) -ne $null }
Test-Check "docker compose v2" {
    docker compose version 2>$null | Out-Null
    $LASTEXITCODE -eq 0
}
Test-Check "secrets dir" { Test-Path $SECRETS_DIR }
Test-Check ".env.dev" { Test-Path (Join-Path $SECRETS_DIR ".env.dev") }
Test-Check ".env.prod" { Test-Path (Join-Path $SECRETS_DIR ".env.prod") }
Test-Check "docker-compose.yml" { Test-Path (Join-Path (Get-OpsComposeRoot) $OpsComposeFile) }
Test-Check "nginx.conf.template" { Test-Path (Join-Path $ROOT "nginx.conf.template") }
Test-Check "nginx.conf" { Test-Path (Join-Path $ROOT "nginx.conf") }
$nginxEnv = Join-Path $SECRETS_DIR "nginx.env"
if (-not (Test-Path $nginxEnv)) {
    Test-Warn "${SECRETS_DIR}/nginx.env" "copy nginx.env.example for production CSP parents"
}
Test-Check "VITE_API_URL in .env.prod" { [bool](Get-EnvValue "VITE_API_URL") }

if ($SERVER) {
    if (-not $Quiet) { Write-Host "  [OK]   DEPLOY_SERVER" -ForegroundColor Green }
    if (-not $SERVER_BASE) {
        Test-Warn "DEPLOY_SERVER_BASE" "set in ops/config/deploy.env for predictable remote paths"
    }
} else {
    Test-Warn "DEPLOY_SERVER" "(needed for remote deploy)"
}

if (Get-EnvValue "DEPLOY_PATH") {
    if (-not $Quiet) { Write-Host "  [OK]   DEPLOY_PATH" -ForegroundColor Green }
} else {
    Test-Warn "DEPLOY_PATH" "(optional in .env.deploy)"
}

if ($Remote -and (Get-EnvValue "DEPLOY_SERVER")) {
    Write-Host ""
    Write-Host "  Remote checks ($SERVER)" -ForegroundColor Cyan
    $pathOk = Invoke-SSHCapture "test -d '$(Get-EnvValue 'DEPLOY_PATH' $DEPLOY_PATH)' && echo ok || echo missing"
    if (($pathOk | Select-Object -Last 1) -match "ok") {
        if (-not $Quiet) { Write-Host "  [OK]   DEPLOY_PATH exists on server" -ForegroundColor Green }
    } else {
        Test-Warn "DEPLOY_PATH on server" "will be created on deploy"
    }
}

if ((Get-Command npm -ErrorAction SilentlyContinue) -and (Test-Path (Join-Path $ROOT "package.json"))) {
    if (-not $Quiet) { Write-Host "  [OK]   npm + package.json" -ForegroundColor Green }
} else {
    Test-Warn "npm" "required for local/dist build"
}

Write-Host ""
if ($errors -gt 0) {
    Write-Host "  $errors failed, $warnings warnings." -ForegroundColor Red
    exit 1
}
Write-Host "  All required checks passed ($warnings warnings)." -ForegroundColor Green
Write-Host ""
exit 0
