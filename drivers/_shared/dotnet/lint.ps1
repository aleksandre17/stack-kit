# .NET driver family - lint: `dotnet format --verify-no-changes` over the module's solution or project
# (the SDK's own formatter and analyzers; nothing is rewritten). Operands pass through.
. (Join-Path $PSScriptRoot "_init.ps1")

$target = Resolve-DotnetModuleTarget -ModuleId $env:STACK_KIT_MODULE_ID -ModPath $OpsModuleRoot -Field "solution"
exit (Invoke-DotnetStep "format" $target (@("--verify-no-changes") + @($args)))
