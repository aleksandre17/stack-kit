# dotnet-aspnet - package: `dotnet publish` of the module into the staging directory the kit names
# (registry `package`: -Output {out}), its declared `publishExpect` paths verified, and release.json
# written beside it. `stack-kit package <module>` runs this, then archives the output with its
# provenance; `stack-kit deploy` ships that archive (ADR-001 amendment 13).
#   package [-Configuration Release] [-Output <dir>]
# The kit CLI forwards arguments as strings, so options are parsed here rather than bound
# by PowerShell (a forwarded "-AllowDirty" string would never bind to a [switch]).
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest = @())

$ErrorActionPreference = "Stop"
$Configuration = $null; $Output = $null; $AllowDirty = $false
for ($i = 0; $i -lt $Rest.Count; $i++) {
    $a = [string]$Rest[$i]
    switch -Regex ($a) {
        '^-AllowDirty$'    { $AllowDirty = $true; continue }
        '^-Configuration$' { if ($i + 1 -ge $Rest.Count) { throw "-Configuration needs a value" }; $Configuration = $Rest[++$i]; continue }
        '^-Output$'        { if ($i + 1 -ge $Rest.Count) { throw "-Output needs a value" }; $Output = $Rest[++$i]; continue }
        default            { throw "dotnet-aspnet package: unknown argument '$a' (supported: -AllowDirty, -Configuration, -Output)" }
    }
}
. (Join-Path $PSScriptRoot "..\_init.ps1")

$moduleId = $env:STACK_KIT_MODULE_ID
$projectRoot = $env:STACK_KIT_PROJECT_ROOT

$dirty = git -C $projectRoot status --porcelain 2>$null
# A dirty checkout is packaged and said so (release.json `dirty`, the archive's `-dirty` id); an
# environment that takes clean releases only refuses it at deploy. -AllowDirty is accepted and moot.
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
Write-Host "[package] $moduleId @ $sha ($Configuration) -> $Output" -ForegroundColor Cyan
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

Write-Host "[package] OK: $Output" -ForegroundColor Green
