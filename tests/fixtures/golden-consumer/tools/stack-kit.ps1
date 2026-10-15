# Consumer shim — delegates to ops/cli/stack-kit.ps1
param([Parameter(ValueFromRemainingArguments=$true)] $args)
& "$PSScriptRoot/../ops/cli/stack-kit.ps1" @args
