# Shared log viewing for manage.ps1 (frontend + portable)

$script:ManageLogSources = @(
    @{ Id = "docker";  Label = "Live container output (docker logs)" },
    @{ Id = "app";     Label = "app.log" },
    @{ Id = "errors";  Label = "error.log" },
    @{ Id = "auth";    Label = "auth.log" },
    @{ Id = "db";      Label = "db.log" },
    @{ Id = "files";   Label = "List all *.log files on server" }
)

function Test-ManageLogSource {
    param([string]$Name)
    ($script:ManageLogSources | ForEach-Object { $_.Id }) -contains $Name
}

function Get-ManageLogFileName {
    param([string]$Source)
    switch ($Source) {
        "app"    { return "app.log" }
        "errors" { return "error.log" }
        "auth"   { return "auth.log" }
        "db"     { return "db.log" }
        default  { return $null }
    }
}

function Select-ManageLogSource {
    if ($script:ManageLogSource) { return $script:ManageLogSource }
    $ids = $script:ManageLogSources | ForEach-Object { $_.Id }
    $hints = $script:ManageLogSources | ForEach-Object { $_.Label }
    $script:ManageLogSource = Select-Option "Log source" $ids $hints
    return $script:ManageLogSource
}

function Select-ManageLogLevel {
    if ($null -ne $script:ManageLogLevel) { return $script:ManageLogLevel }
    $choice = Select-Option "Log level filter" @("ALL", "ERROR", "WARN", "INFO") @(
        "No filter", "ERROR lines only", "WARN lines only", "INFO lines only"
    )
    $script:ManageLogLevel = if ($choice -eq "ALL") { "" } else { $choice }
    return $script:ManageLogLevel
}

function Resolve-ManageLogArgs {
    param([string]$Arg1, [string]$Arg2, [string]$Arg3)
    $script:ManageLogSource = $null
    $script:ManageLogLevel = $null
    foreach ($a in @($Arg1, $Arg2, $Arg3)) {
        if (-not $a) { continue }
        if (Test-ManageLogSource $a) { $script:ManageLogSource = $a }
        elseif ($a -in @("ALL", "ERROR", "WARN", "INFO")) {
            $script:ManageLogLevel = if ($a -eq "ALL") { "" } else { $a }
        }
    }
}

function Invoke-ManageLogs {
    param(
        [string]$ContainerName,
        [string]$DeployPath,
        [string]$LogSource,
        [string]$LogLevel,
        [string]$RemoteKind
    )

    Assert-Env @("DEPLOY_SERVER")

    $grepSuffix = ""
    if ($LogLevel) {
        $grepSuffix = "| grep -E '$LogLevel'"
    }

    switch ($LogSource) {
        "docker" {
            & ssh @(Get-StackKitSshExtraArgs) $SERVER "docker logs -f --tail=100 $ContainerName"
        }
        "files" {
            $remoteScript = @"
echo '--- log files under deploy path ---'
find '$DeployPath' -name '*.log' 2>/dev/null | head -80 | while read -r f; do ls -lh "`$f"; done
[ -d '$DeployPath/logs' ] && ls -lah '$DeployPath/logs' 2>/dev/null || true
"@
            Invoke-SSHCapture $remoteScript | ForEach-Object { Write-Host $_ }
        }
        default {
            $file = Get-ManageLogFileName $LogSource
            if (-not $file) {
                Write-Host "  [ERROR] Unknown log source: $LogSource" -ForegroundColor Red
                exit 1
            }
            $remoteScript = @"
if [ -f '$DeployPath/logs/$file' ]; then tail -f '$DeployPath/logs/$file' $grepSuffix
elif [ -f '$DeployPath/$file' ]; then tail -f '$DeployPath/$file' $grepSuffix
else echo '[remote] Log file not found: $file (tried logs/ and deploy root)'; exit 1
fi
"@
            & ssh @(Get-StackKitSshExtraArgs) $SERVER $remoteScript
        }
    }
}
