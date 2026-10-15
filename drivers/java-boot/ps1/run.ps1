# java-boot — local run via manifest (host + secrets .env.dev)
if (-not $env:STACK_KIT_MODULE_ID) {
    throw 'STACK_KIT_MODULE_ID required - run: stack-kit {alias} run | stack-kit hybrid boot {alias}'
}
$DriverRoot = Split-Path $PSScriptRoot -Parent
$PackageRoot = Split-Path (Split-Path $DriverRoot -Parent) -Parent
$env:STACK_KIT_KIT_ROOT = $PackageRoot

& (Join-Path $PackageRoot "toolkit\hybrid\Invoke-HybridRun.ps1") -ModuleId $env:STACK_KIT_MODULE_ID
exit $LASTEXITCODE
