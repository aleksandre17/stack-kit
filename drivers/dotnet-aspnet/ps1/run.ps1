# dotnet-aspnet - local run via manifest (host process + secrets .env.dev)
# Same delegate as the other drivers' run.ps1: the shared hybrid runner imports the module's
# secrets and then dot-sources the launch script this driver DECLARES (registry hybrid.script).
if (-not $env:GEOSTAT_MODULE_ID) {
    throw 'GEOSTAT_MODULE_ID required - run: geostat {alias} run | geostat hybrid boot {alias}'
}
$DriverRoot = Split-Path $PSScriptRoot -Parent
$PackageRoot = Split-Path (Split-Path $DriverRoot -Parent) -Parent
$env:GEOSTAT_KIT_ROOT = $PackageRoot

& (Join-Path $PackageRoot "toolkit\hybrid\Invoke-HybridRun.ps1") -ModuleId $env:GEOSTAT_MODULE_ID
exit $LASTEXITCODE
