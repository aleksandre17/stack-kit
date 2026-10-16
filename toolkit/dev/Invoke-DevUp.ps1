# stack-kit — smart dev startup orchestrator.
#
# Usage: stack-kit dev up [alias|moduleId|all] [--mode hybrid|local|docker|remote] [--no-infra] [--no-tunnel]
#
# Modes (auto-detected when not set):
#   hybrid   Apps on host (Windows), infra remote Docker + SSH tunnel.  Default when DEPLOY_SERVER set.
#   local    Apps on host only — no infra management.                   Default when DEPLOY_SERVER not set.
#   docker   Full stack via stack-kit stack up -d --build.                Ignores per-module target.
#   remote   Source on Windows, rsync → Linux server, Docker reloads.
#
# Nothing here knows a driver name or a consumer's module vocabulary: roles, boot order
# and the remote-watch argv are all DECLARED (drivers/registry.json, the manifest) and
# read back; help text renders from the resolved manifest, or shows placeholders.

param(
    [Parameter(Position = 0)]
    [string]$SubCommand = "help",
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$DevArgs = @()
)

$ErrorActionPreference = "Stop"
$PackageRoot = if ($env:STACK_KIT_KIT_ROOT) { $env:STACK_KIT_KIT_ROOT } else {
    Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
}
. (Join-Path $PackageRoot "lib\project.ps1")
. (Join-Path $PackageRoot "lib\env.ps1")
. (Join-Path $PackageRoot "lib\drivers.ps1")
. (Join-Path $PackageRoot "lib\modules.ps1")

$Root = Get-ProjectRootFromManifest
if (-not $Root) {
    Write-Host "[dev] stack-kit.json not found (run: stack-kit init)" -ForegroundColor Red
    exit 1
}

# Default boot order by role: catalogs.roles `bootOrder`; a consumer may declare its own as dev.bootOrder.
$DefaultBootOrder = @(Get-KitContextLines 'roles:bootOrder')

# ── Helpers ───────────────────────────────────────────────────────────────────

function Write-DevLog {
    param([string]$Message, [string]$Level = "INFO")
    $color = switch ($Level) {
        "ERROR" { "Red" }
        "WARN"  { "Yellow" }
        "OK"    { "Green" }
        default { "Cyan" }
    }
    Write-Host "[dev] $Message" -ForegroundColor $color
}

function Get-BootOrder {
    $declared = @(Get-ManifestList "dev.bootOrder")
    if ($declared.Count -gt 0) { return $declared }
    return $DefaultBootOrder
}

function Show-DevHelp {
    $aliases = Get-CliAliasesFromManifest
    $aliasLine = if ($aliases.Count -gt 0) {
        ($aliases.GetEnumerator() | ForEach-Object { "$($_.Key)->$($_.Value)" }) -join ", "
    } else { "(none — declare cli.aliases in the manifest)" }

    # Examples are RENDERED from the resolved manifest; with no manifest aliases we show
    # placeholders. Kit help never teaches one consumer's module vocabulary.
    $sample = @($aliases.GetEnumerator() | Sort-Object Key)
    $a1 = if ($sample.Count -ge 1) { $sample[0].Key }  else { "<alias>" }
    $m1 = if ($sample.Count -ge 1) { $sample[0].Value } else { "<moduleId>" }
    $a2 = if ($sample.Count -ge 2) { $sample[1].Key }  else { "<alias>" }
    $m2 = if ($sample.Count -ge 2) { $sample[1].Value } else { "<moduleId>" }

    Write-Host @"

  stack-kit dev — smart development startup (stack-kit)

    stack-kit dev up <alias|moduleId|all> [flags]

  Modes (auto-detected from ops/config/deploy.env DEPLOY_SERVER):
    hybrid    Apps on host + infra remote Docker + SSH tunnel  [default when DEPLOY_SERVER set]
    local     Apps on host only; no infra management           [default otherwise]
    docker    Full stack via compose (stack-kit stack up)
    remote    rsync source → Linux server, Docker reloads

  Flags:
    --mode <hybrid|local|docker|remote>   Override auto-detected mode
    --no-infra                            Skip infra remote up (infra already running)
    --no-tunnel                           Skip SSH tunnel (tunnel already open)

  Targets:
    <alias>     any key of cli.aliases in the manifest
    <moduleId>  any key of modules in the manifest
    all         Boot every module in new windows, in declared boot order
                (remote mode: each module gets its own watch window)

  Examples:
    stack-kit dev up $a1                  # $m1, hybrid mode (auto)
    stack-kit dev up $a2 --no-tunnel      # $m2, skip tunnel
    stack-kit dev up all                  # all modules in new windows
    stack-kit dev up $a1 --mode local     # $m1, local only
    stack-kit dev up $a1 --mode remote    # rsync source → server, docker reloads
    stack-kit dev up all --mode remote    # all modules as remote watch

  CLI aliases: $aliasLine

"@
}

function Resolve-DevTarget {
    param([string]$Raw)
    if ($Raw -eq "all") { return "all" }
    Resolve-CliAlias $Raw
}

function Get-DevMode {
    param([string]$ExplicitMode)
    if ($ExplicitMode) { return $ExplicitMode.ToLower().Trim() }
    $server = Get-DeployEnvValue "DEPLOY_SERVER"
    if ($server) { return "hybrid" }
    return "local"
}

function Get-StackKitScript {
    $rel = Get-ManifestField "vscode.cliScript"
    if (-not $rel) { $rel = "tools/stack-kit.ps1" }
    Join-Path $Root ($rel -replace '/', '\')
}

function Start-ModuleInNewWindow {
    param([string]$ModuleId)
    $gs = Get-StackKitScript
    Write-DevLog "Opening window: $ModuleId"
    Start-Process powershell -ArgumentList @(
        '-NoExit',
        '-ExecutionPolicy', 'Bypass',
        '-Command',
        "& '$gs' hybrid boot $ModuleId"
    )
}

function Start-TunnelInNewWindow {
    $gs = Get-StackKitScript
    Write-DevLog "Opening SSH tunnel window (Ctrl+C in that window to close tunnel)"
    Start-Process powershell -ArgumentList @(
        '-NoExit',
        '-ExecutionPolicy', 'Bypass',
        '-Command',
        "& '$gs' infra tunnel"
    )
    Write-DevLog "Waiting 4 s for tunnel to establish..."
    Start-Sleep -Seconds 4
}

function Get-ModulesInRoleOrder {
    $mods = Get-ProjectModules
    $order = [System.Collections.ArrayList]@()
    $seen  = @{}
    foreach ($role in (Get-BootOrder)) {
        foreach ($mid in $mods) {
            if ((Get-ModuleRole $mid) -eq $role -and -not $seen[$mid]) {
                [void]$order.Add($mid)
                $seen[$mid] = $true
            }
        }
    }
    foreach ($mid in $mods) {
        if (-not $seen[$mid]) { [void]$order.Add($mid) }
    }
    return @($order)
}

# ── Entry point ───────────────────────────────────────────────────────────────

if ($SubCommand -in @("help", "", $null)) { Show-DevHelp; exit 0 }

if ($SubCommand -ne "up") {
    Write-DevLog "Unknown subcommand: '$SubCommand'. Run: stack-kit dev help" "ERROR"
    exit 1
}

# Parse DevArgs ────────────────────────────────────────────────────────────────
$target       = ""
$explicitMode = ""
$skipInfra    = $false
$skipTunnel   = $false

$i = 0
while ($i -lt $DevArgs.Count) {
    $a = [string]$DevArgs[$i]
    switch -Exact ($a) {
        "--no-infra"  { $skipInfra = $true }
        "--no-tunnel" { $skipTunnel = $true }
        "--mode" {
            if (($i + 1) -lt $DevArgs.Count) {
                $explicitMode = [string]$DevArgs[$i + 1]
                $i++
            }
        }
        default {
            if (-not $a.StartsWith("--") -and -not $target) { $target = $a }
        }
    }
    $i++
}

if (-not $target) {
    Write-DevLog "Usage: stack-kit dev up <alias|moduleId|all> [--mode hybrid|local|docker|remote] [--no-infra] [--no-tunnel]" "ERROR"
    exit 1
}

$mode = Get-DevMode $explicitMode
Write-DevLog "mode=$mode  target=$target  skip-infra=$skipInfra  skip-tunnel=$skipTunnel"

# ── Docker mode ───────────────────────────────────────────────────────────────
if ($mode -eq "docker") {
    Write-DevLog "Starting full stack via Docker Compose (stack-kit stack up -d --build)"
    $gs = Get-StackKitScript
    & $gs stack up -d --build
    exit $LASTEXITCODE
}

# ── Remote watch mode ─────────────────────────────────────────────────────────
# Source stays on Windows; the driver's declared devWatch argv rsyncs to the Linux
# server and reloads the container. Requires DEPLOY_SERVER + DEPLOY_LAYOUT=structured.
if ($mode -eq "remote") {
    $gs = Get-StackKitScript
    $server = Get-DeployEnvValue "DEPLOY_SERVER"
    if (-not $server) {
        Write-DevLog "DEPLOY_SERVER not set in ops/config/deploy.env — remote watch requires a server." "ERROR"
        exit 1
    }

    function Get-RemoteWatchCommand {
        param([string]$ModuleId)
        $modType = Get-ManifestField "modules.$ModuleId.type"
        $argv = Get-DriverTaskArgs -Type $modType -TaskName "devWatch"
        if (-not $argv -or $argv.Count -eq 0) {
            Write-DevLog "Driver '$modType' declares no tasks.devWatch in drivers/registry.json — $ModuleId cannot be watched remotely." "ERROR"
            return $null
        }
        Write-DevLog "remote watch: $ModuleId ($modType) -> $server"
        return @($gs, $ModuleId) + $argv
    }

    if ($target -eq "all") {
        $ordered = Get-ModulesInRoleOrder
        if ($ordered.Count -eq 0) { Write-DevLog "No modules in manifest" "ERROR"; exit 1 }
        $opened = 0
        foreach ($mid in $ordered) {
            $cmd = Get-RemoteWatchCommand $mid
            if (-not $cmd) { continue }
            $cmdStr = "& '" + ($cmd -join "' '") + "'"
            Start-Process powershell -ArgumentList @('-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', $cmdStr)
            $opened++
            Start-Sleep -Milliseconds 500
        }
        if ($opened -eq 0) { Write-DevLog "No module declares a devWatch task." "ERROR"; exit 1 }
        Write-DevLog "$opened remote watch window(s) opened." "OK"
        exit 0
    }

    $resolved = Resolve-DevTarget $target
    if (-not $resolved) {
        Write-DevLog "Unknown target: '$target'" "ERROR"
        exit 1
    }
    $cmdArgs = Get-RemoteWatchCommand $resolved
    if (-not $cmdArgs) { exit 1 }
    & $cmdArgs[0] $cmdArgs[1..($cmdArgs.Count - 1)]
    exit $LASTEXITCODE
}

# ── Infra + tunnel (hybrid only) ──────────────────────────────────────────────
if ($mode -eq "hybrid") {
    if (-not $skipInfra) {
        Write-DevLog "Starting remote infra (stack-kit infra remote up)..."
        $gs = Get-StackKitScript
        & $gs infra remote up
        if ($LASTEXITCODE -ne 0) {
            Write-DevLog "infra remote up failed (exit $LASTEXITCODE). Pass --no-infra to skip." "ERROR"
            exit $LASTEXITCODE
        }
        Write-DevLog "Infra started" "OK"
    } else {
        Write-DevLog "Skipping infra remote up (--no-infra)"
    }

    if (-not $skipTunnel) {
        Start-TunnelInNewWindow
    } else {
        Write-DevLog "Skipping tunnel (--no-tunnel)"
    }
}

# ── Boot modules ─────────────────────────────────────────────────────────────
if ($target -eq "all") {
    $ordered = Get-ModulesInRoleOrder
    if ($ordered.Count -eq 0) {
        Write-DevLog "No modules found in manifest" "ERROR"
        exit 1
    }
    Write-DevLog "Opening windows for: $($ordered -join ', ')"
    foreach ($mid in $ordered) {
        Start-ModuleInNewWindow $mid
        Start-Sleep -Milliseconds 500
    }
    Write-DevLog "All module windows opened. Infra + apps should start shortly." "OK"
    exit 0
}

$resolved = Resolve-DevTarget $target
if (-not $resolved) {
    Write-DevLog "Unknown target: '$target'. Check cli.aliases in stack-kit.json or use a module id." "ERROR"
    Write-DevLog "Known aliases: $((Get-CliAliasesFromManifest).GetEnumerator() | ForEach-Object { "$($_.Key)->$($_.Value)" } | Out-String)"
    exit 1
}

Write-DevLog "Booting $resolved..."
$env:STACK_KIT_MODULE_ID = $resolved
$runScript = Get-DriverCommandPath -ModuleId $resolved -Command "run"
& $runScript
exit $LASTEXITCODE
