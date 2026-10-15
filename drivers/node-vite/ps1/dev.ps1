# ==================================================================
#  dev.ps1 — Windows edit -> Linux compose/dev + Docker (no dist build)
#
#  bootstrap | sync | watch | restart
#  Stack-agnostic SPA: Vite, Angular, Nx (see toolkit/Dev-Remote.ps1)
# ==================================================================
param(
    [Parameter(Position = 0)]
    [string]$SubCommand = "help",
    [ValidateSet("dev", "prod")]
    [string]$Environment = "dev",
    [int]$DebounceMs = 1500,
    [switch]$NoBuild,
    [switch]$NoInitialSync
)

$driverArgs = @($SubCommand) + $args
if ($driverArgs -contains "help" -or $driverArgs -contains "-h" -or $driverArgs -contains "--help") {
    Write-Host ""
    Write-Host "  dev.ps1 — remote dev (source sync, compose dev on Linux)" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  bootstrap   First rsync + env + docker compose up (--build)" -ForegroundColor White
    Write-Host "  sync        Incremental rsync only (no npm build, no restart)" -ForegroundColor White
    Write-Host "  watch       Debounced rsync on save (Ctrl+C to stop)" -ForegroundColor White
    Write-Host "  restart     docker compose restart on server" -ForegroundColor White
    Write-Host ""
    Write-Host "  -Environment dev|prod   -DebounceMs 1500   bootstrap: -NoBuild" -ForegroundColor Gray
    Write-Host "  Requires: rsync (Git for Windows), DEPLOY_SERVER, compose dev override" -ForegroundColor Gray
    Write-Host "  Prod static UI: use deploy dist|sync — not dev.ps1" -ForegroundColor Gray
    Write-Host ""
    exit 0
}

. "$PSScriptRoot\_common.ps1"
$GetComposeServices = Join-Path $env:STACK_KIT_KIT_ROOT "toolkit\powershell\Get-ComposeServices.ps1"
. $GetComposeServices

$validSubs = @("bootstrap", "sync", "watch", "restart")
if ($SubCommand -in @("", "help")) {
    $SubCommand = "help"
}
if ($SubCommand -eq "help") {
    Write-Host ""
    Write-Host "  dev.ps1 — remote dev on Linux (source rsync, NO npm build)" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  bootstrap | sync | watch | restart" -ForegroundColor White
    Write-Host ""
    Write-Host "  NOT the same as deploy watch:" -ForegroundColor Yellow
    Write-Host "    <alias> deploy watch  ->  npm build + dist/ + nginx (static prod-like)" -ForegroundColor Gray
    Write-Host "    <alias> dev watch     ->  rsync src only + Vite in container" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  Example: stack-kit <alias> dev bootstrap -Environment dev" -ForegroundColor Gray
    Write-Host "           stack-kit <alias> dev watch" -ForegroundColor Gray
    Write-Host ""
    exit 0
}
if ($SubCommand -notin $validSubs) {
    Write-Host "  [ERROR] Unknown dev subcommand: $SubCommand" -ForegroundColor Red
    Write-Host "  Valid: $($validSubs -join ' | ')" -ForegroundColor Yellow
    exit 1
}

if ($DebounceMs -lt 400) { $DebounceMs = 400 }

$extraCompose = if ($Environment -eq "dev") { @("docker-compose.override.yml") } else { @("docker-compose.prod.yml") }
$_services = @(Get-ComposeServicesFromFile -ModuleRoot $ROOT -ComposeFile "docker-compose.yml" -ExtraComposeFiles $extraCompose)
$_serviceNames = @($_services | ForEach-Object { $_.Name })

if ($_services.Count -eq 1) {
    $ServiceName = $_services[0].Name
} elseif ($_services.Count -gt 1) {
    $ServiceName = Select-Option "Select Service" $_serviceNames ($_services | ForEach-Object { $_.Dockerfile })
} else {
    Write-Host "  [ERROR] No services in docker-compose.yml" -ForegroundColor Red
    exit 1
}

Set-Service ($_services | Where-Object { $_.Name -eq $ServiceName })
Assert-Env @("DEPLOY_SERVER", "DEPLOY_HOST_PORT")

$kind = if ($Environment -eq "dev") { "compose-dev" } else { "compose-prod" }
Set-DeployPathForMode -Kind $kind

$TIMESTAMP = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$script:LOG_FILE = Join-Path $LOG_DIR "dev-${SubCommand}-${ServiceName}-$Environment`_$TIMESTAMP.log"
$_serverHost = $SERVER -replace '^.*@', ''
$startTime = Get-Date

LogBanner "$APP_NAME - dev $SubCommand ($Environment)" @{
    Server = $SERVER
    Deploy = $DEPLOY_PATH
    Port   = $HOST_PORT
}

switch ($SubCommand) {
    "bootstrap" {
        LogSection "[1/3] rsync source (no dist/)"
        $rc = Invoke-DevRsyncToRemote
        if ($rc -ne 0) { exit 1 }

        LogSection "[2/3] Upload env + compose up"
        $build = -not $NoBuild
        $rc = Invoke-DevRemoteComposeUp -Environment $Environment -Build:$build
        if ($rc -ne 0) { Log "compose up FAILED" "ERROR"; exit 1 }

        LogSection "[3/3] Manifest"
        Write-RemoteDeployManifest -Environment $Environment -DeployMode "dev-bootstrap" -Kind $kind
        Log "Live: http://${_serverHost}:$HOST_PORT (Vite/Angular dev in container)" "OK"
    }

    "sync" {
        LogSection "rsync only"
        $rc = Invoke-DevRsyncToRemote
        if ($rc -ne 0) { exit 1 }
        Log "Files on server updated; container uses volume/watch — no restart" "OK"
        Log "URL: http://${_serverHost}:$HOST_PORT" "INFO"
    }

    "restart" {
        LogSection "compose restart"
        $rc = Invoke-DevRemoteComposeRestart -Environment $Environment
        if ($rc -ne 0) { exit 1 }
        Log "Restarted on server" "OK"
    }

    "watch" {
        $watchRoots = Get-DevWatchRoots
        if ($watchRoots.Count -eq 0) {
            Write-Host "  [ERROR] Nothing to watch under $BUILD_CONTEXT" -ForegroundColor Red
            exit 1
        }

        $global:devWatchLastChange = $null
        $script:devWatchBusy = $false
        $script:devWatchQueued = $false

        function Invoke-DevWatchSync {
            if ($script:devWatchBusy) {
                $script:devWatchQueued = $true
                return
            }
            $script:devWatchBusy = $true
            try {
                LogSection "rsync"
                $null = Invoke-DevRsyncToRemote
            } finally {
                $script:devWatchBusy = $false
                if ($script:devWatchQueued) {
                    $script:devWatchQueued = $false
                    $global:devWatchLastChange = Get-Date
                }
            }
        }

        function Register-DevWatchPath {
            param([string]$Path, [System.Collections.Generic.List[System.IO.FileSystemWatcher]]$Collect)
            if (-not (Test-Path $Path)) { return }
            $w = New-Object System.IO.FileSystemWatcher
            if ((Get-Item $Path).PSIsContainer) {
                $w.Path = $Path
                $w.Filter = "*.*"
                $w.IncludeSubdirectories = $true
            } else {
                $w.Path = Split-Path $Path -Parent
                $w.Filter = Split-Path $Path -Leaf
                $w.IncludeSubdirectories = $false
            }
            $w.NotifyFilter = [IO.NotifyFilters]'FileName, LastWrite, DirectoryName'
            $w.EnableRaisingEvents = $true
            foreach ($evt in @("Changed", "Created", "Deleted", "Renamed")) {
                Register-ObjectEvent -InputObject $w -EventName $evt -SourceIdentifier "stack-kit-dev-$($Collect.Count)-$evt" -Action {
                    $p = $Event.SourceEventArgs.FullPath
                    if ($p -match '[\\/](node_modules|dist|build|\.git|\.angular|coverage)([\\/]|$)') { return }
                    $global:devWatchLastChange = Get-Date
                } | Out-Null
            }
            [void]$Collect.Add($w)
        }

        if (-not $NoInitialSync) {
            Invoke-DevWatchSync
        }

        $watchers = [System.Collections.Generic.List[System.IO.FileSystemWatcher]]::new()
        foreach ($root in $watchRoots) { Register-DevWatchPath -Path $root -Collect $watchers }

        Write-Host ""
        Write-Host "  dev watch [source rsync]: debounce ${DebounceMs}ms. Ctrl+C to stop." -ForegroundColor Cyan
        Write-Host "  (For static dist loop use: stack-kit <alias> deploy watch)" -ForegroundColor DarkGray
        Write-Host "  Run dev bootstrap once if container is not up." -ForegroundColor Gray
        Write-Host ""

        try {
            while ($true) {
                Start-Sleep -Milliseconds 200
                if ($null -eq $global:devWatchLastChange) { continue }
                $elapsed = ((Get-Date) - $global:devWatchLastChange).TotalMilliseconds
                if ($elapsed -lt $DebounceMs) { continue }
                $global:devWatchLastChange = $null
                Invoke-DevWatchSync
            }
        } finally {
            Get-EventSubscriber | Where-Object { $_.SourceIdentifier -like 'stack-kit-dev-*' } |
                ForEach-Object { Unregister-Event -SubscriptionId $_.SubscriptionId -ErrorAction SilentlyContinue }
            foreach ($w in $watchers) {
                $w.EnableRaisingEvents = $false
                $w.Dispose()
            }
        }
        exit 0
    }
}

LogDone $startTime
