# java-boot - test: the module's tests (Gradle `test`, Maven `test`). Operands pass through.
$PackageRoot = $env:STACK_KIT_KIT_ROOT
. (Join-Path $PackageRoot "lib\project.ps1")
. (Join-Path $PackageRoot "lib\drivers.ps1")
. (Join-Path $PSScriptRoot "_build-tool.ps1")
exit (Invoke-JvmStep -ModuleId $env:STACK_KIT_MODULE_ID -Step "test" -Rest @($args))
