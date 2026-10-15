# dotnet-aspnet driver init - set $env:STACK_KIT_MODULE_ID before dot-sourcing
if (-not $env:STACK_KIT_MODULE_ID) {
    throw "STACK_KIT_MODULE_ID required - run: stack-kit mod <moduleId> <command> (see stack-kit help)"
}

$DriverRoot = $PSScriptRoot
$PackageRoot = Split-Path (Split-Path $DriverRoot -Parent) -Parent
$env:STACK_KIT_KIT_ROOT = $PackageRoot
. (Join-Path $PackageRoot "lib\project.ps1")
. (Join-Path $PackageRoot "lib\drivers.ps1")

if (-not $env:STACK_KIT_PROJECT_ROOT) {
    $env:STACK_KIT_PROJECT_ROOT = Get-ProjectRootFromManifest
}
if (-not $env:STACK_KIT_PROJECT_ROOT) { throw "project manifest not found" }

$modPath = Get-ModuleProjectPath $env:STACK_KIT_MODULE_ID
$entry = Get-ModuleManifestEntry $env:STACK_KIT_MODULE_ID

$OpsModuleRoot = $modPath
$OpsScriptRoot = $OpsModuleRoot
$OpsSecretsModule = if ($entry.secretsModule) { $entry.secretsModule } else { $env:STACK_KIT_MODULE_ID }
$OpsComposeFile = "docker-compose.yml"

$OpsToolkitRoot = Get-OpsToolkitPowerShellRoot
. (Join-Path $OpsToolkitRoot "_common.ps1")
. (Join-Path $DriverRoot "ps1\_project.ps1")
