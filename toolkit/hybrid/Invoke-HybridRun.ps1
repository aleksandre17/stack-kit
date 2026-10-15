# Local app run: host process + manifest secrets (.env.dev over .env.prod); optional remote infra via tunnel.
# Every driver DECLARES its launch step (drivers/registry.json "hybrid": {"script": ...}), dot-sourced
# here with $ModuleId, $modPath, $root and $PackageRoot in scope; this file names no driver (ADR-001 K6).
param(
    [Parameter(Mandatory = $true)]
    [string]$ModuleId
)

$ErrorActionPreference = "Stop"

$PackageRoot = if ($env:STACK_KIT_KIT_ROOT) { $env:STACK_KIT_KIT_ROOT } else {
    Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
}
. (Join-Path $PackageRoot "lib\project.ps1")
. (Join-Path $PackageRoot "lib\env.ps1")
. (Join-Path $PackageRoot "lib\drivers.ps1")
. (Join-Path $PackageRoot "lib\module-manifest.ps1")

$root = Get-ProjectRootFromManifest
if (-not $root) { throw "$((Get-KitIdentity).manifestFilename) not found" }

$entry = Get-ModuleManifestEntry $ModuleId
if (-not $entry) { throw "Unknown module: $ModuleId" }

$modPath = Get-ModuleProjectPath $ModuleId
$secretsModule = Get-ModuleSecretsFolder $ModuleId
Import-ModuleRunEnv $secretsModule

$driverType = Get-ModuleType $ModuleId
Write-Host "[hybrid] boot $ModuleId ($driverType) env=$(Join-Path (Get-SecretsModuleDir $secretsModule) '.env.dev')" -ForegroundColor Cyan

$hybridScript = Get-DriverHybridScript $driverType
if (-not $hybridScript) {
    throw ('Hybrid run not supported for driver type ''{0}'' (module {1}) - declare "hybrid": {{"script": ...}} in its drivers registry' -f $driverType, $ModuleId)
}
Set-Location $modPath
. $hybridScript
exit $LASTEXITCODE
