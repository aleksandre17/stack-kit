# node-vite driver init — set $env:GEOSTAT_MODULE_ID before dot-sourcing
if (-not $env:GEOSTAT_MODULE_ID) {
    throw "GEOSTAT_MODULE_ID required - run: geostat mod <moduleId> <command> (see geostat help)"
}

$DriverRoot = Split-Path $PSScriptRoot -Parent
$PackageRoot = Split-Path $DriverRoot -Parent
$env:GEOSTAT_KIT_ROOT = $PackageRoot
. (Join-Path $PackageRoot "lib\project.ps1")
. (Join-Path $PackageRoot "lib\drivers.ps1")

if (-not $env:GEOSTAT_PROJECT_ROOT) {
    $env:GEOSTAT_PROJECT_ROOT = Get-ProjectRootFromManifest
}
if (-not $env:GEOSTAT_PROJECT_ROOT) { throw "geostat.ops.json not found" }

$modPath = Get-ModuleProjectPath $env:GEOSTAT_MODULE_ID
$entry = Get-ModuleManifestEntry $env:GEOSTAT_MODULE_ID

$OpsModuleRoot = $modPath
$OpsScriptRoot = $OpsModuleRoot
$OpsSecretsModule = if ($entry.secretsModule) { $entry.secretsModule } else { $env:GEOSTAT_MODULE_ID }
$OpsComposeFile = "docker-compose.yml"
# modules.<id>.composeDir: compose authority outside the source tree (default: module path)
$OpsComposeRoot = if ($entry.composeDir) {
    Join-Path $env:GEOSTAT_PROJECT_ROOT ($entry.composeDir -replace '[\\/]', [System.IO.Path]::DirectorySeparatorChar)
} else { $OpsModuleRoot }

if (Test-Path (Join-Path $OpsModuleRoot "ops.config.ps1")) {
    . (Join-Path $OpsModuleRoot "ops.config.ps1")
}

$OpsToolkitRoot = Get-OpsToolkitPowerShellRoot
. (Join-Path $OpsToolkitRoot "_common.ps1")
. (Join-Path $OpsToolkitRoot "Deploy-Path.ps1")
. (Join-Path $OpsToolkitRoot "Dev-Remote.ps1")
. (Join-Path $OpsToolkitRoot "Static-Deploy-Watch.ps1")
