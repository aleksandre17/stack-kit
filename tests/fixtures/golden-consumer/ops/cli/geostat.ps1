# Project CLI — delegates into the geostat-kit package.
param([Parameter(ValueFromRemainingArguments=$true)] $args)
& "$PSScriptRoot/../../kits/geostat-kit/cli/geostat.ps1" @args
