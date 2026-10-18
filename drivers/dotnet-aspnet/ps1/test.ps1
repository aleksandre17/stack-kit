# dotnet-aspnet - test: `dotnet test` of the module's tests (dotnet.test: a test project or
# solution, module-relative), else its solution or project. `"test": ""` declares the module has
# none, said and counted as not run. Operands pass through to dotnet.
#
# A run that discovers no test fails, as pytest's and Jest's do: a target holding no test is not a
# tested module (CWE-223). The count is read from the TRX report every `dotnet test` can write.
. (Join-Path $PSScriptRoot "..\_init.ps1")

$target = Resolve-DotnetModuleTarget -ModuleId $env:STACK_KIT_MODULE_ID -ModPath $OpsModuleRoot -Field "test"
if (-not $target) {
    Write-StepNotRun "  [$env:STACK_KIT_MODULE_ID test] declared none (modules.$env:STACK_KIT_MODULE_ID.dotnet.test = `"`")" "declared none"
    exit 0
}
$configuration = Get-DotnetOption -ModuleId $env:STACK_KIT_MODULE_ID -Name "configuration" -Default "Release"
$results = Join-Path ([System.IO.Path]::GetTempPath()) ("stack-kit-test-" + [guid]::NewGuid().ToString("N"))
try {
    $code = Invoke-DotnetStep "test" $target (@("-c", [string]$configuration, "--nologo", "--logger", "trx", "--results-directory", $results) + @($args))
    if ($code -ne 0) { exit $code }
    # Every count the reports carry is summed and said: a skipped test is not one that passed.
    # A test the run skipped is counted only as the gap between `total` and `executed` (xUnit's skip
    # leaves `notExecuted` at 0), so that gap is what is said.
    $count = @{ total = 0; executed = 0; passed = 0 }
    if (Test-Path -LiteralPath $results) {
        foreach ($report in Get-ChildItem -LiteralPath $results -Filter "*.trx" -Recurse) {
            $counters = ([xml](Get-Content -LiteralPath $report.FullName -Raw)).TestRun.ResultSummary.Counters
            foreach ($name in @($count.Keys)) { $count[$name] += [int]$counters.$name }
        }
    }
    if ($count.total -eq 0) {
        Write-Host "  [$env:STACK_KIT_MODULE_ID test] no test was discovered in $target - a module with none declares it: modules.$env:STACK_KIT_MODULE_ID.dotnet.test = `"`"" -ForegroundColor Red
        exit 1
    }
    Write-Host "  [$env:STACK_KIT_MODULE_ID test] $($count.total) test(s): $($count.passed) passed, $($count.total - $count.executed) not executed (skipped)" -ForegroundColor Green
    exit 0
}
finally {
    if (Test-Path -LiteralPath $results) { Remove-Item -LiteralPath $results -Recurse -Force }
}
