# Docker Compose — secrets/<module> (.env.dev | .env.prod)
param([switch]$Prod)

. (Join-Path $PSScriptRoot "..\_init.ps1")

$envArgs = Get-ComposeEnvFileArgs -Module $OpsSecretsModule -Environment $(if ($Prod) { "prod" } else { "dev" })
$fileArgs = if ($Prod) {
    @("-f", "docker-compose.yml", "-f", "docker-compose.prod.yml")
} else {
    @()
}

Push-Location $OpsModuleRoot
try {
    & docker compose @envArgs @fileArgs @args
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
