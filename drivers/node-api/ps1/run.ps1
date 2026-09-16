# node-api — local run via manifest (host process + secrets .env.dev)
# Mirror of java-boot/ps1/run.ps1 and node-vite/ps1/run.ps1: delegates to the shared
# hybrid runner, which dispatches on the module's driver type (node-api -> pnpm script).
if (-not $env:GEOSTAT_MODULE_ID) {
    throw 'GEOSTAT_MODULE_ID required - run: geostat {alias} run | geostat hybrid boot {alias}'
}
$DriverRoot = Split-Path $PSScriptRoot -Parent
$PackageRoot = Split-Path (Split-Path $DriverRoot -Parent) -Parent
$env:GEOSTAT_KIT_ROOT = $PackageRoot

& (Join-Path $PackageRoot "toolkit\hybrid\Invoke-HybridRun.ps1") -ModuleId $env:GEOSTAT_MODULE_ID
exit $LASTEXITCODE
