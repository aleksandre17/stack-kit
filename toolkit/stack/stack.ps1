# stack-kit stack shortcut
param([switch]$Prod, [Parameter(ValueFromRemainingArguments = $true)]$Remaining)
& (Join-Path $PSScriptRoot "compose.ps1") -Prod:$Prod @Remaining
exit $LASTEXITCODE
