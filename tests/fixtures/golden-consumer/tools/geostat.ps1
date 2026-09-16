# Consumer shim — delegates to ops/cli/geostat.ps1
param([Parameter(ValueFromRemainingArguments=$true)] $args)
& "$PSScriptRoot/../ops/cli/geostat.ps1" @args
