# Project CLI entry — delegates to stack-kit package
param(
    [Parameter(Position = 0)]
    [string]$Command = "help",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliRest = @()
)
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
& (Join-Path $Root "kits\stack-kit\cli\stack-kit.ps1") -Command $Command -CliRest $CliRest
exit $LASTEXITCODE
