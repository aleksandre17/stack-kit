# A Node module's lifecycle step (build | test | lint | start): the package.json script the module's
# driver DECLARES for it (registry `packageScripts`), or the module's own name for it
# (`modules.<id>.node.scripts.<step>`; "" declares that the module has none). Every driver that
# declares `packageScripts` is given these steps as commands (lib/modules.py driver_commands); this
# file names no driver and no framework (ADR-001 amendment 8).
#
# The package manager is the module's `node.packageManager`, else the one whose lockfile is nearest
# above the module (pnpm-lock.yaml, yarn.lock, package-lock.json), else npm. Dependencies are
# installed first when node_modules is absent, from the lockfile (a fresh clone builds as-is).
# A `lint` the package does not have is skipped and said; a missing `build` or `test` fails.
param(
    [string]$ModuleId = $env:STACK_KIT_MODULE_ID,
    [string]$Step = $env:STACK_KIT_COMMAND
)

$ErrorActionPreference = "Stop"
if (-not $ModuleId -or -not $Step) {
    throw 'a module and a step are required - run: stack-kit mod <module> <build|test|lint>'
}

$PackageRoot = if ($env:STACK_KIT_KIT_ROOT) { $env:STACK_KIT_KIT_ROOT } else {
    Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
}
. (Join-Path $PackageRoot "lib\project.ps1")
. (Join-Path $PackageRoot "lib\drivers.ps1")

#: Steps a package may lack without failing (catalogs.lifecycle `optional`): asked for, never required.
$OptionalSteps = @(Get-KitContextLines 'lifecycle:optional')

$root = Get-ProjectRootFromManifest
$modPath = Get-ModuleProjectPath $ModuleId
$typ = Get-ModuleType $ModuleId
$packageJson = Join-Path $modPath "package.json"
if (-not (Test-Path $packageJson -PathType Leaf)) {
    Write-Host "  [$ModuleId $Step] no package.json in $modPath" -ForegroundColor Red
    exit 1
}

# The script: the module's own name for the step, else the one its driver declares.
$entry = Get-ModuleManifestEntry $ModuleId
$own = $null
if ($entry.node -and $entry.node.scripts -and $entry.node.scripts.PSObject.Properties[$Step]) {
    $own = [string]$entry.node.scripts.$Step
}
$script = if ($null -ne $own) { $own } else { Get-KitContextValue "driver:$($typ):packageScript:$Step" }
if ($null -ne $own -and $own -eq "") {
    Write-Host "  [$ModuleId $Step] declared none (modules.$ModuleId.node.scripts.$Step = `"`")" -ForegroundColor DarkGray
    exit 0
}
if (-not $script) {
    Write-Host "  [$ModuleId $Step] driver '$typ' declares no package script for '$Step'" -ForegroundColor Red
    exit 1
}
$scripts = (Get-Content $packageJson -Raw -Encoding UTF8 | ConvertFrom-Json).scripts
if (-not ($scripts -and $scripts.PSObject.Properties[$script])) {
    if ($OptionalSteps -contains $Step) {
        Write-Host "  [$ModuleId $Step] skipped: package.json has no '$script' script" -ForegroundColor DarkGray
        exit 0
    }
    Write-Host "  [$ModuleId $Step] package.json has no '$script' script - add it, or name another in modules.$ModuleId.node.scripts.$Step (`"`" = none)" -ForegroundColor Red
    exit 1
}

# The package manager and the directory its lockfile is in (the workspace root, for a workspace).
$lockfiles = [ordered]@{ "pnpm-lock.yaml" = "pnpm"; "yarn.lock" = "yarn"; "package-lock.json" = "npm" }
$pm = if ($entry.node -and $entry.node.packageManager) { [string]$entry.node.packageManager } else { $null }
$workspace = $modPath
$dir = $modPath
while ($dir) {
    $hit = @($lockfiles.Keys | Where-Object { Test-Path (Join-Path $dir $_) }) | Select-Object -First 1
    if ($hit) {
        $workspace = $dir
        if (-not $pm) { $pm = $lockfiles[$hit] }
        break
    }
    if ($dir -eq $root) { break }
    $parent = Split-Path $dir -Parent
    if (-not $parent -or $parent -eq $dir) { break }
    $dir = $parent
}
if (-not $pm) { $pm = "npm" }
if (-not (Get-Command $pm -ErrorAction SilentlyContinue)) {
    Write-Host "  [$ModuleId $Step] '$pm' is not on PATH" -ForegroundColor Red
    exit 1
}

function Invoke-Native {
    param([string]$Where, [string[]]$Argv)
    Write-Host "  [$ModuleId $Step] $pm $($Argv -join ' ')  ($Where)" -ForegroundColor Cyan
    Push-Location $Where
    # The tool speaks to the console as it runs; only its exit code is this function's answer.
    try { & $pm @Argv | Out-Host; return $LASTEXITCODE } finally { Pop-Location }
}

if (-not (Test-Path (Join-Path $workspace "node_modules")) -and -not (Test-Path (Join-Path $modPath "node_modules"))) {
    $frozen = @{
        "npm"  = $(if (Test-Path (Join-Path $workspace "package-lock.json")) { @("ci") } else { @("install") })
        "pnpm" = @("install", "--frozen-lockfile")
        "yarn" = @("install", "--frozen-lockfile")
    }
    $install = if ($frozen.ContainsKey($pm)) { $frozen[$pm] } else { @("install") }
    $code = Invoke-Native $workspace $install
    if ($code -ne 0) { exit $code }
}

# A build runs the workspace scripts the module declares must build before it, in order.
if ($Step -eq "build" -and $entry.node -and $entry.node.prebuildScripts) {
    foreach ($pre in @($entry.node.prebuildScripts)) {
        $code = Invoke-Native $workspace @("run", [string]$pre)
        if ($code -ne 0) { exit $code }
    }
}

$code = Invoke-Native $modPath @("run", $script)
exit $code
