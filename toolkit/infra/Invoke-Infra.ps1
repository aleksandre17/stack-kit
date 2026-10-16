# stack-kit — the infra stack (Postgres, Redis, Qdrant ...) on THIS machine.
# Usage: stack-kit infra local up|down|status [-Prod]
# On a target, the infra stack is the delivery engine's (`stack-kit infra remote ...`, `infra tunnel`):
# it lives in the layout's infra place and runs under the target's declared compose invocation.

param(
    [Parameter(Position = 0)]
    [string]$Mode = "help",
    [Parameter(Position = 1)]
    [string]$Action = "",
    [switch]$Prod,
    [switch]$Confirm
)

$ErrorActionPreference = "Stop"
$PackageRoot = if ($env:STACK_KIT_KIT_ROOT) {
    $env:STACK_KIT_KIT_ROOT
} else {
    (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

. (Join-Path $PackageRoot "lib\project.ps1")
. (Join-Path $PackageRoot "lib\env.ps1")

$Root = Get-ProjectRootFromManifest
if (-not $Root) {
    Write-Host "[infra] stack-kit.json not found" -ForegroundColor Red
    exit 1
}
$env:STACK_KIT_PROJECT_ROOT = $Root

$InfraComposeDir = Get-InfraComposeDirFromManifest
$SecretsInfra = Join-Path (Get-SecretsRoot) "infra"

function Write-InfraLog {
    param([string]$Message, [string]$Level = "INFO")
    $color = switch ($Level) {
        "ERROR" { "Red" }
        "WARN" { "Yellow" }
        default { "Cyan" }
    }
    Write-Host "[infra] $Message" -ForegroundColor $color
}

function Resolve-InfraEnvFile {
    if ($Prod) {
        $f = Join-Path $SecretsInfra ".env.prod"
        if (-not (Test-Path $f)) { $f = Join-Path $SecretsInfra ".env.dev" }
        return $f
    }
    return Join-Path $SecretsInfra ".env.dev"
}

function Assert-InfraEnvFile {
    $f = Resolve-InfraEnvFile
    if (-not (Test-Path $f)) {
        Write-InfraLog "Missing $f - copy from ops/config/infra/.env.example" "ERROR"
        exit 1
    }
    return $f
}

function Resolve-InfraComposeFileArgs {
    param([bool]$IsProd)
    try {
        $null = Get-InfraComposeIncludeFiles
    }
    catch {
        Write-InfraLog $_.Exception.Message "ERROR"
        exit 1
    }
    $files = [System.Collections.ArrayList]@()
    Add-InfraComposeFileArgs -Target $files
    if ($IsProd) {
        $prod = Join-Path $InfraComposeDir "docker-compose.prod.yml"
        if (Test-Path $prod) { [void]$files.AddRange(@('-f', $prod)) }
        $coexist = Join-Path $InfraComposeDir "docker-compose.coexist.yml"
        if (Test-Path $coexist) { [void]$files.AddRange(@('-f', $coexist)) }
    }
    return $files.ToArray()
}

function Invoke-InfraLocalCompose {
    param([string]$ComposeAction)
    $envFile = Assert-InfraEnvFile
    $composeArgs = Resolve-InfraComposeFileArgs -IsProd $Prod
    Push-Location $InfraComposeDir
    try {
        # This machine's compose invocation is the runtime catalog's (the entry flagged `local`).
        $compose = @(Invoke-KitResolver -Arguments @('compose-command'))
        $cmd = @($compose | Select-Object -Skip 1) + $composeArgs + @('--env-file', $envFile) + @($ComposeAction -split ' ')
        Write-InfraLog "$($compose[0]) $($cmd -join ' ')"
        & $compose[0] @cmd
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    finally {
        Pop-Location
    }
}


function Show-InfraHelp {
    Write-Host @"

  stack-kit infra - the infra stack (stack.infra.services)

    local up|down|status   Docker on this machine (-Prod: .env.prod + docker-compose.prod.yml)
    remote sync|up|down|status|purge   on the target, in its layout's infra place (the Python CLI)
    tunnel                 ssh -L to the target's infra ports (the Python CLI)

  Compose dir: stack.infraComposeDir in the manifest

"@
}

$bash = Get-Command bash -ErrorAction SilentlyContinue
switch ($Mode.ToLowerInvariant()) {
    "help" { Show-InfraHelp; exit 0 }
    "local" {
        switch ($Action.ToLowerInvariant()) {
            "up" { Invoke-InfraLocalCompose "up -d" }
            "down" { Invoke-InfraLocalCompose "down" }
            "status" { Invoke-InfraLocalCompose "ps" }
            default { Write-InfraLog "Usage: stack-kit infra local up|down|status" "ERROR"; exit 1 }
        }
    }
    { $_ -in @("remote", "tunnel", "prereqs") } {
        Write-InfraLog "infra $Mode runs on the target through the CLI: stack-kit infra remote <action> --target <t> --env <id> (prereqs: stack-kit targets --verify)" "ERROR"
        exit 2
    }
    default { Write-InfraLog "Usage: stack-kit infra remote up|down|sync|status|purge -Confirm" "ERROR"; exit 1 }
        }
    }
    "tunnel" { Start-InfraTunnel }
    default {
        Write-InfraLog "Unknown mode: $Mode" "ERROR"
        Show-InfraHelp
        exit 1
    }
}
