# .NET driver family init (dotnet-aspnet, dotnet-library) - set $env:STACK_KIT_MODULE_ID before dot-sourcing
if (-not $env:STACK_KIT_MODULE_ID) {
    throw "STACK_KIT_MODULE_ID required - run: stack-kit mod <moduleId> <command> (see stack-kit help)"
}

# drivers/_shared/dotnet -> the kit root
$PackageRoot = Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent
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
. (Join-Path $PackageRoot "lib\env.ps1")
$SECRETS_DIR = Get-SecretsModuleDir -Module $OpsSecretsModule
. (Join-Path $PSScriptRoot "_project.ps1")
