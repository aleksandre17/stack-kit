# The kit's former command name (ADR-001 decision 1): one notice, then the current command.
# Nothing here holds a rule; the names are read from lib/identity.json.
# A simple param block on purpose: an advanced one (any [Parameter()]) adds PowerShell's common
# parameters, and an operand such as `-d` then binds as -Debug and is lost (ADR-001 K3).
param([string]$Command = "help", [string[]]$CliRest = @())
$CliRest = @($CliRest) + @($args)
. (Join-Path $PSScriptRoot "..\lib\project.ps1")
$id = Get-KitIdentity
Write-KitDeprecation "cli/$($id.legacyKitName).ps1" "cli/$($id.kitName).ps1"
& (Join-Path $PSScriptRoot "$($id.kitName).ps1") -Command $Command -CliRest $CliRest
exit $LASTEXITCODE
