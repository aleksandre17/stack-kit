# Pre-flight - a .NET module (dotnet-aspnet, dotnet-library)
# What is checked follows what the module's driver declares, never its name: the secrets and
# .env.dev of a module the host runs (`run`), the publishExpect of one that is packaged (`package`).
# Advanced script: an argument it does not declare is a binding error, never silently ignored.
[CmdletBinding()]
param(
    [switch]$Quiet
)

. (Join-Path $PSScriptRoot "_init.ps1")

$errors = 0
$warnings = 0

function Test-Check {
    param([string]$Label, [scriptblock]$Test)
    if (& $Test) {
        if (-not $Quiet) { Write-Host "  [OK]   $Label" -ForegroundColor Green }
    } else {
        Write-Host "  [FAIL] $Label" -ForegroundColor Red
        $script:errors++
    }
}
function Test-Warn {
    param([string]$Label, [string]$Msg = "")
    if (-not $Quiet) { Write-Host "  [WARN] $Label $Msg" -ForegroundColor Yellow }
    $script:warnings++
}

Write-Host ""
$caps = @(Get-DriverCapabilities $env:STACK_KIT_MODULE_ID)
Write-Host "  Pre-flight ($env:STACK_KIT_MODULE_ID, $(Get-ModuleType $env:STACK_KIT_MODULE_ID))" -ForegroundColor Cyan
Write-Host ""

Test-Check "dotnet SDK" { (Get-Command dotnet -ErrorAction SilentlyContinue) -ne $null }
Test-Check "module path" { Test-Path $OpsModuleRoot -PathType Container }

$project = $null
try {
    $project = Resolve-DotnetProjectFile -ModuleId $env:STACK_KIT_MODULE_ID -ModPath $OpsModuleRoot
    if (-not $Quiet) { Write-Host "  [OK]   project file ($project)" -ForegroundColor Green }
} catch {
    Write-Host "  [FAIL] project file - $($_.Exception.Message)" -ForegroundColor Red
    $errors++
}

if ($caps -contains "run") {
    if (Test-Path $SECRETS_DIR) {
        if (-not $Quiet) { Write-Host "  [OK]   secrets dir" -ForegroundColor Green }
    } else {
        Test-Warn "secrets dir" "($SECRETS_DIR) - create it and keep it out of version control"
    }
    if (-not (Test-Path (Join-Path $SECRETS_DIR ".env.dev"))) {
        Test-Warn ".env.dev" "local run uses appsettings only (ASP.NET reads KEY__SUB=value env vars)"
    }
}

if ($caps -contains "package") {
    $expect = @(Get-DotnetOption -ModuleId $env:STACK_KIT_MODULE_ID -Name "publishExpect" -Default @())
    if ($expect.Count -eq 0) {
        Test-Warn "dotnet.publishExpect" "not declared - deploy artifact checks only that publish succeeded"
    }
}

Write-Host ""
if ($errors -gt 0) {
    Write-Host "  $errors failed, $warnings warnings." -ForegroundColor Red
    exit 1
}
Write-Host "  All required checks passed ($warnings warnings)." -ForegroundColor Green
Write-Host ""
exit 0
