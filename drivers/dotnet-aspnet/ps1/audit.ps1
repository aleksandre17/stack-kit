# dotnet-aspnet - audit: the module's NuGet dependencies, transitive included, against the advisories
# the SDK knows (`dotnet list package --vulnerable`); a high or critical one fails the step.
. (Join-Path $PSScriptRoot "..\_init.ps1")

$target = Resolve-DotnetModuleTarget -ModuleId $env:STACK_KIT_MODULE_ID -ModPath $OpsModuleRoot -Field "solution"
$out = & dotnet list $target package --vulnerable --include-transitive 2>&1 | Out-String
Write-Host $out
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if ($out -match '(?im)^\s*>.*\b(High|Critical)\b') {
    Write-Host "  [audit] a high or critical advisory -- upgrade the package (or record why not)" -ForegroundColor Red
    exit 1
}
exit 0
