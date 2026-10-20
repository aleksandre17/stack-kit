# dotnet-aspnet - launch step, dot-sourced by toolkit/hybrid/Invoke-HybridRun.ps1 after the
# module's .env.prod/.env.dev were imported into the process environment.
# ASP.NET Core reads environment variables natively ("ConnectionStrings__DefaultConnection"),
# so secrets reach the app without being written into appsettings files.
# In scope from the caller: $ModuleId, $modPath, $root.

. (Join-Path $PSScriptRoot "..\..\_shared\dotnet\_project.ps1")

$project = Resolve-DotnetProjectFile -ModuleId $ModuleId -ModPath $modPath
$runArgs = @("run", "--project", $project)

$launchProfile = Get-DotnetOption -ModuleId $ModuleId -Name "launchProfile"
if ($launchProfile) { $runArgs += @("--launch-profile", [string]$launchProfile) }

Write-Host "[hybrid] dotnet $($runArgs -join ' ')" -ForegroundColor Cyan
& dotnet @runArgs
exit $LASTEXITCODE
