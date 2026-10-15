# dotnet-aspnet - local run via manifest (host process + secrets .env.dev)
# Same delegate as the other drivers' run.ps1: the shared hybrid runner imports the module's
# secrets and then dot-sources the launch script this driver DECLARES (registry hybrid.script).
if (-not $env:STACK_KIT_MODULE_ID) {
    throw 'STACK_KIT_MODULE_ID required - run: stack-kit {alias} run | stack-kit hybrid boot {alias}'
}
$DriverRoot = Split-Path $PSScriptRoot -Parent
$PackageRoot = Split-Path (Split-Path $DriverRoot -Parent) -Parent
$env:STACK_KIT_KIT_ROOT = $PackageRoot

& (Join-Path $PackageRoot "toolkit\hybrid\Invoke-HybridRun.ps1") -ModuleId $env:STACK_KIT_MODULE_ID
exit $LASTEXITCODE
