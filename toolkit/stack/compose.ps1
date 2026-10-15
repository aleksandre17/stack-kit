# Full stack compose runner (manifest: stack.composeDir)
param([switch]$Prod)

$PackageRoot = $PSScriptRoot | Split-Path -Parent | Split-Path -Parent
. (Join-Path $PackageRoot "lib\project.ps1")
. (Join-Path $PackageRoot "lib\env.ps1")
. (Join-Path $PackageRoot "lib\modules.ps1")
$Root = Get-ProjectRootFromManifest
if (-not $Root) { throw "stack-kit.json not found" }

$composeRel = Get-ManifestField "stack.composeDir" "ops/compose/stack"
$ComposeDir = Join-Path $Root $composeRel

$envArgs = Get-StackComposeEnvFileArgs -Environment $(if ($Prod) { "prod" } else { "dev" })
$fileArgs = if ($Prod) { @("-f", "docker-compose.prod.yml") } else { @("-f", "docker-compose.yml") }

Push-Location $ComposeDir
try {
    Write-Host ""
    $stackName = Get-DeployEnvValue "COMPOSE_PROJECT_NAME" (Split-Path $Root -Leaf)
    Write-Host "  $stackName stack ($(if ($Prod) { 'prod' } else { 'dev' }))" -ForegroundColor Cyan
    Write-StackEndpointHints
    Write-Host ""
    & docker compose @envArgs @fileArgs @args
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
