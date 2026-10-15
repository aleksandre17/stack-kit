# dotnet-aspnet - deploy
#   deploy artifact [-Configuration Release] [-Output <dir>] [-AllowDirty]
#       dotnet publish into <project>/build/publish/<moduleId>/<short-sha>/ and write release.json.
#       This is the whole deploy contract of this driver: it produces one verifiable artifact.
#   deploy remote
#       Refused. Delivering the artifact to a host (IIS, a VM, a container registry) is not
#       declared by this driver yet; an unsupported path is an explicit refusal, never a guess.
# The kit CLI forwards arguments as strings, so options are parsed here rather than bound
# by PowerShell (a forwarded "-AllowDirty" string would never bind to a [switch]).
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest = @())

$ErrorActionPreference = "Stop"
$Action = "artifact"; $Configuration = $null; $Output = $null; $AllowDirty = $false
for ($i = 0; $i -lt $Rest.Count; $i++) {
    $a = [string]$Rest[$i]
    switch -Regex ($a) {
        '^-AllowDirty$'    { $AllowDirty = $true; continue }
        '^-Configuration$' { if ($i + 1 -ge $Rest.Count) { throw "-Configuration needs a value" }; $Configuration = $Rest[++$i]; continue }
        '^-Output$'        { if ($i + 1 -ge $Rest.Count) { throw "-Output needs a value" }; $Output = $Rest[++$i]; continue }
        '^-'               { throw "dotnet-aspnet deploy: unknown option '$a' (supported: -AllowDirty, -Configuration, -Output)" }
        default            { $Action = $a }
    }
}
. (Join-Path $PSScriptRoot "..\_init.ps1")

$moduleId = $env:GEOSTAT_MODULE_ID
$projectRoot = $env:GEOSTAT_PROJECT_ROOT

switch ($Action) {
    "artifact" { }
    "remote" {
        throw "dotnet-aspnet: 'deploy remote' is not supported by this driver. Build with 'deploy artifact' and deliver it with the project's runbook."
    }
    default {
        throw "dotnet-aspnet: unknown deploy action '$Action' (supported: artifact, remote)"
    }
}

$dirty = git -C $projectRoot status --porcelain 2>$null
if ($dirty -and -not $AllowDirty) {
    throw "Working tree is dirty. Commit first, or pass -AllowDirty for a non-release build."
}
$sha = (git -C $projectRoot rev-parse --short HEAD 2>$null)
if (-not $sha) { $sha = "nogit" }
$sha = $sha.Trim()

if (-not $Configuration) {
    $Configuration = [string](Get-DotnetOption -ModuleId $moduleId -Name "configuration" -Default "Release")
}
if (-not $Output) {
    $Output = Join-Path $projectRoot "build\publish\$moduleId\$sha"
}

$project = Resolve-DotnetProjectFile -ModuleId $moduleId -ModPath $OpsModuleRoot
Write-Host "[deploy] $moduleId @ $sha ($Configuration) -> $Output" -ForegroundColor Cyan
& dotnet publish $project -c $Configuration -o $Output -nologo
if ($LASTEXITCODE -ne 0) { throw "dotnet publish failed with exit code $LASTEXITCODE" }

$expect = @(Get-DotnetOption -ModuleId $moduleId -Name "publishExpect" -Default @())
foreach ($rel in $expect) {
    if (-not (Test-Path (Join-Path $Output $rel))) {
        throw "Publish output is incomplete: declared '$rel' is missing (modules.$moduleId.dotnet.publishExpect)"
    }
}

$commit = (git -C $projectRoot rev-parse HEAD 2>$null)
[ordered]@{
    module        = $moduleId
    commit        = if ($commit) { $commit.Trim() } else { $null }
    dirty         = [bool]$dirty
    configuration = $Configuration
    builtAtUtc    = (Get-Date).ToUniversalTime().ToString("o")
    dotnetSdk     = (dotnet --version).Trim()
    verified      = $expect
} | ConvertTo-Json | Set-Content -Path (Join-Path $Output "release.json") -Encoding utf8

Write-Host "[deploy] OK: $Output" -ForegroundColor Green
