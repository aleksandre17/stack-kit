# Project CLI — delegates into the stack-kit package.
param([Parameter(ValueFromRemainingArguments=$true)] $args)
& "$PSScriptRoot/../../kits/stack-kit/cli/stack-kit.ps1" @args
