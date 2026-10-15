# node-api — local run via manifest (host process + secrets .env.dev)
# Mirror of java-boot/ps1/run.ps1 and node-vite/ps1/run.ps1: delegates to the shared
# hybrid runner, which dispatches on the module's driver type (node-api -> pnpm script).
if (-not $env:STACK_KIT_MODULE_ID) {
    throw 'STACK_KIT_MODULE_ID required - run: stack-kit {alias} run | stack-kit hybrid boot {alias}'
}
$DriverRoot = Split-Path $PSScriptRoot -Parent
$PackageRoot = Split-Path (Split-Path $DriverRoot -Parent) -Parent
$env:STACK_KIT_KIT_ROOT = $PackageRoot

& (Join-Path $PackageRoot "toolkit\hybrid\Invoke-HybridRun.ps1") -ModuleId $env:STACK_KIT_MODULE_ID
exit $LASTEXITCODE
