# Static deploy file watcher: npm build + scp dist + nginx reload (prod-like server UI)
# Dot-source after _common.ps1 / Deploy-Path.ps1. Not for remote dev source sync (use dev.ps1 watch).

function Start-FeStaticDeployWatch {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("dev", "prod")][string]$Environment,
        [int]$DebounceMs = 3000,
        [switch]$NoInitialSync
    )
    if ($DebounceMs -lt 500) { $DebounceMs = 500 }

    Set-DeployPathForMode -Kind "static"
    $_serverHost = $script:SERVER -replace '^.*@', ''

    $watchRoots = @(
        (Join-Path $script:BUILD_CONTEXT "src"),
        (Join-Path $script:BUILD_CONTEXT "public"),
        (Join-Path $script:BUILD_CONTEXT "index.html")
    ) | Where-Object { Test-Path $_ }

    $viteConfigs = Get-ChildItem -Path $script:BUILD_CONTEXT -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^vite\.config\.(ts|js|mts|mjs)$' }
    foreach ($cfg in $viteConfigs) { $watchRoots += $cfg.FullName }

    if ($watchRoots.Count -eq 0) {
        Write-Host "  [ERROR] Nothing to watch under $($script:BUILD_CONTEXT)" -ForegroundColor Red
        exit 1
    }

    $global:stackKitStaticWatchLastChange = $null
    $script:staticWatchBusy = $false
    $script:staticWatchQueued = $false

    function Invoke-StaticWatchPublish {
        if ($script:staticWatchBusy) {
            $script:staticWatchQueued = $true
            return
        }
        $script:staticWatchBusy = $true
        try {
            LogSection "deploy watch: build + sync ($Environment)"
            $rc = Invoke-FeStaticPublishCycle -Environment $Environment -LogFile $script:LOG_FILE -ReloadNginx -DeployMode "sync"
            if ($rc -ne 0) { Log "deploy watch FAILED (exit $rc)" "ERROR" }
            else { Log "Live: http://${_serverHost}:$($script:HOST_PORT)" "OK" }
        } finally {
            $script:staticWatchBusy = $false
            if ($script:staticWatchQueued) {
                $script:staticWatchQueued = $false
                $global:stackKitStaticWatchLastChange = Get-Date
            }
        }
    }

    function Register-StaticWatchPath {
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
            Register-ObjectEvent -InputObject $w -EventName $evt -SourceIdentifier "stack-kit-static-watch-$($Collect.Count)-$evt" -Action {
                $p = $Event.SourceEventArgs.FullPath
                if ($p -match '[\\/](dist|node_modules|\.git)([\\/]|$)') { return }
                $global:stackKitStaticWatchLastChange = Get-Date
            } | Out-Null
        }
        [void]$Collect.Add($w)
    }

    LogBanner "$($script:APP_NAME) - deploy watch [static dist] ($Environment)" @{
        DebounceMs = $DebounceMs
        Deploy     = $script:DEPLOY_PATH
        Watching   = ($watchRoots -join "; ")
    }

    Write-Host ""
    Write-Host "  Mode: npm build -> dist/ -> nginx reload on server (NOT source rsync)." -ForegroundColor DarkGray
    Write-Host "  Remote dev (save -> rsync only):  stack-kit fe dev watch" -ForegroundColor DarkGray
    Write-Host ""

    if (-not $NoInitialSync) { Invoke-StaticWatchPublish }

    $watchers = [System.Collections.Generic.List[System.IO.FileSystemWatcher]]::new()
    foreach ($root in $watchRoots) { Register-StaticWatchPath -Path $root -Collect $watchers }

    Write-Host "  deploy watch: debounce ${DebounceMs}ms. Ctrl+C to stop." -ForegroundColor Cyan
    Write-Host ""

    try {
        while ($true) {
            Start-Sleep -Milliseconds 250
            if ($null -eq $global:stackKitStaticWatchLastChange) { continue }
            $elapsed = ((Get-Date) - $global:stackKitStaticWatchLastChange).TotalMilliseconds
            if ($elapsed -lt $DebounceMs) { continue }
            $global:stackKitStaticWatchLastChange = $null
            Invoke-StaticWatchPublish
        }
    } finally {
        Get-EventSubscriber | Where-Object { $_.SourceIdentifier -like 'stack-kit-static-watch-*' } |
            ForEach-Object { Unregister-Event -SubscriptionId $_.SubscriptionId -ErrorAction SilentlyContinue }
        foreach ($w in $watchers) {
            $w.EnableRaisingEvents = $false
            $w.Dispose()
        }
    }
}
