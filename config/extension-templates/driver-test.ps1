# <name> - test: the command that runs the module's tests, run from the module directory; operands pass through.
# The launcher runs it as `mod <module> test`; its exit code is the step's verdict.
$PackageRoot = $env:STACK_KIT_KIT_ROOT
. (Join-Path $PackageRoot "lib\project.ps1")
$modPath = Get-ModuleProjectPath $env:STACK_KIT_MODULE_ID
Push-Location $modPath
try {
    # <<pending: the test command line, e.g. & ./tool test @args>>
    exit $LASTEXITCODE
} finally { Pop-Location }
