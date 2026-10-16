# dotnet-aspnet - build: `dotnet build` of the module's solution (dotnet.solution) or project,
# in its configuration (dotnet.configuration, default Release). Operands pass through to dotnet.
. (Join-Path $PSScriptRoot "..\_init.ps1")

$target = Resolve-DotnetModuleTarget -ModuleId $env:STACK_KIT_MODULE_ID -ModPath $OpsModuleRoot -Field "solution"
$configuration = Get-DotnetOption -ModuleId $env:STACK_KIT_MODULE_ID -Name "configuration" -Default "Release"
exit (Invoke-DotnetStep "build" $target (@("-c", [string]$configuration, "--nologo") + @($args)))
