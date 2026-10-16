# java-boot - build: the module's Gradle `build` without its tests (`-x test`; `test` runs them).
# Operands pass through to Gradle.
$PackageRoot = $env:STACK_KIT_KIT_ROOT
. (Join-Path $PackageRoot "lib\project.ps1")
. (Join-Path $PackageRoot "lib\drivers.ps1")
. (Join-Path $PSScriptRoot "_gradle.ps1")
exit (Invoke-GradleStep -ModuleId $env:STACK_KIT_MODULE_ID -Task "build" -Rest (@("-x", "test") + @($args)))
