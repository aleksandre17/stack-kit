# stack-kit CLI launcher: everything is the Python CLI's (cli/stack_kit.py -> lib/cli), the same verbs
# in a terminal and in CI (ADR-001 amendment 13). This file only finds Python and passes the
# command line through, unchanged.
# A simple param block on purpose: an advanced one (any [Parameter()]) adds PowerShell's common
# parameters, and an operand such as `-d` then binds as -Debug and is lost (ADR-001 K3).
param([string]$Command = "help", [string[]]$CliRest = @())
$CliRest = @($CliRest) + @($args)
$PackageRoot = Split-Path $PSScriptRoot -Parent
. (Join-Path $PackageRoot "lib\stack-kit-python.ps1")
$py = Get-StackKitPythonArgs
if (-not $py) { Write-Host "  [ERROR] Python 3 is required (tried py -3, python3, python)" -ForegroundColor Red; exit 9009 }
Invoke-StackKitPythonExe $py "-B" (Join-Path $PSScriptRoot "stack_kit.py") $Command @CliRest
exit $LASTEXITCODE
