# Local app run: host process + the module's configuration for ONE environment (.env, then .env.dev;
# production's .env.prod only with -Environment prod / --env prod); optional remote infra via tunnel.
# Every driver DECLARES its launch step (drivers/registry.json "hybrid": {"script": ...}), dot-sourced
# here with $ModuleId, $modPath, $root and $PackageRoot in scope; this file names no driver (ADR-001 K6).
# It is also every such driver's `run` command (lib/modules.py driver_commands): dispatched as one, it
# reads the module from STACK_KIT_MODULE_ID, which the dispatch sets (ADR-001 amendment 7).
# The module is named (-ModuleId) or the dispatch's; every operand is read for `--env <dev|prod>`,
# so a stray word is never taken for a module.
[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$ModuleId = $env:STACK_KIT_MODULE_ID,
    [string]$Environment = "",
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest = @()
)
for ($i = 0; $i -lt $Rest.Count; $i++) {
    if ($Rest[$i] -eq "--env" -and $i + 1 -lt $Rest.Count) { $Environment = $Rest[++$i] }
}
. (Join-Path $(if ($env:STACK_KIT_KIT_ROOT) { $env:STACK_KIT_KIT_ROOT } else { Split-Path (Split-Path $PSScriptRoot -Parent) -Parent }) "lib\project.ps1")
if (-not $Environment) { $Environment = Get-KitContextValue 'environment:run' }
$null = Test-KitEnvironment $Environment

$ErrorActionPreference = "Stop"
if (-not $ModuleId) {
    throw 'a module is required - run: stack-kit <alias> run | stack-kit hybrid boot <alias>'
}

$PackageRoot = if ($env:STACK_KIT_KIT_ROOT) { $env:STACK_KIT_KIT_ROOT } else {
    Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
}
. (Join-Path $PackageRoot "lib\project.ps1")
. (Join-Path $PackageRoot "lib\env.ps1")
. (Join-Path $PackageRoot "lib\drivers.ps1")

$root = Get-ProjectRootFromManifest
if (-not $root) { throw "$((Get-KitIdentity).manifestFilename) not found" }

$entry = Get-ModuleManifestEntry $ModuleId
if (-not $entry) { throw "Unknown module: $ModuleId" }

$modPath = Get-ModuleProjectPath $ModuleId
$secretsModule = Get-ModuleSecretsFolder $ModuleId
Import-ModuleRunEnv $secretsModule -Environment $Environment

$driverType = Get-ModuleType $ModuleId
Write-Host "[hybrid] boot $ModuleId ($driverType) env=$Environment ($(Join-Path (Get-SecretsModuleDir $secretsModule) ".env.$Environment"))" -ForegroundColor Cyan

$hybridScript = Get-DriverHybridScript $driverType
if (-not $hybridScript) {
    throw ('Hybrid run not supported for driver type ''{0}'' (module {1}) - declare "hybrid": {{"script": ...}} in its drivers registry' -f $driverType, $ModuleId)
}
Set-Location $modPath
. $hybridScript
exit $LASTEXITCODE
