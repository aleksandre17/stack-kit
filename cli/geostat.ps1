# The kit's former command name (ADR-001 decision 1): one notice, then the current command.
# Nothing here holds a rule; the names are read from lib/identity.json.
param(
    [Parameter(Position = 0)]
    [string]$Command = "help",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliRest = @()
)
. (Join-Path $PSScriptRoot "..\lib\project.ps1")
$id = Get-KitIdentity
Write-KitDeprecation "cli/$($id.legacyKitName).ps1" "cli/$($id.kitName).ps1"
& (Join-Path $PSScriptRoot "$($id.kitName).ps1") -Command $Command -CliRest $CliRest
exit $LASTEXITCODE
