# Shim — canonical entry: ops/cli/stack-kit.ps1
# CMD.exe: use tools\stack-kit.cmd
param(
    [Parameter(Position = 0)]
    [string]$Command = "help",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliRest = @()
)
$Root = Split-Path $PSScriptRoot -Parent
& (Join-Path $Root "ops\cli\stack-kit.ps1") -Command $Command -CliRest $CliRest
exit $LASTEXITCODE
