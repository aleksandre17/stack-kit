# Project CLI entry — delegates to stack-kit package
# A simple param block on purpose: an advanced one (any [Parameter()]) adds PowerShell's common
# parameters, and an operand such as `-d` then binds as -Debug and is lost (ADR-001 K3).
param([string]$Command = "help", [string[]]$CliRest = @())
$CliRest = @($CliRest) + @($args)
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
& (Join-Path $Root "kits\stack-kit\cli\stack-kit.ps1") -Command $Command -CliRest $CliRest
exit $LASTEXITCODE
