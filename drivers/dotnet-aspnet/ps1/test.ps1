# dotnet-aspnet - test: `dotnet test` of the module's tests (dotnet.test: a test project or
# solution, module-relative), else its solution or project. `"test": ""` declares the module has
# none, said and passed. Operands pass through to dotnet.
. (Join-Path $PSScriptRoot "..\_init.ps1")

$target = Resolve-DotnetModuleTarget -ModuleId $env:STACK_KIT_MODULE_ID -ModPath $OpsModuleRoot -Field "test"
if (-not $target) {
    Write-Host "  [$env:STACK_KIT_MODULE_ID test] declared none (modules.$env:STACK_KIT_MODULE_ID.dotnet.test = `"`")" -ForegroundColor DarkGray
    exit 0
}
$configuration = Get-DotnetOption -ModuleId $env:STACK_KIT_MODULE_ID -Name "configuration" -Default "Release"
exit (Invoke-DotnetStep "test" $target (@("-c", [string]$configuration, "--nologo") + @($args)))
