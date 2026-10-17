# java-boot - build: the module's build without its tests (Gradle `build -x test`, Maven `package
# -DskipTests`; `test` runs them). Operands pass through to the build tool.
$PackageRoot = $env:STACK_KIT_KIT_ROOT
. (Join-Path $PackageRoot "lib\project.ps1")
. (Join-Path $PackageRoot "lib\drivers.ps1")
. (Join-Path $PSScriptRoot "_build-tool.ps1")
exit (Invoke-JvmStep -ModuleId $env:STACK_KIT_MODULE_ID -Step "build" -Rest @($args))
