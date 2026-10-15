# ==================================================================
#  manage.ps1  -  Multi-package container management
#
#  Usage:
#    .\manage.ps1                      interactive: pick package + command
#    .\manage.ps1 <package>            interactive: pick command for package
#    .\manage.ps1 <command>            interactive: pick package for command
#    .\manage.ps1 <command> <package>  direct (order doesn't matter)
#    .\manage.ps1 <package> <command>  direct (order doesn't matter)
#
#  Commands:  status | logs | restart | undeploy | delete
# ==================================================================
param(
    [Parameter(Position=0)] [string]$Arg1 = "",
    [Parameter(Position=1)] [string]$Arg2 = "",
    [Parameter(Position=2)] [string]$Arg3 = ""
)

. "$PSScriptRoot\_common.ps1"
$OpsPkg = Join-Path $env:STACK_KIT_KIT_ROOT "toolkit\powershell"
. (Join-Path $OpsPkg "Get-ComposeServices.ps1")
. (Join-Path $OpsPkg "Manage-Logs.ps1")

$_validCommands = @("status", "logs", "restart", "reload", "config", "rebuild", "stop", "start", "undeploy", "delete", "rm", "nuke")
$_commandHints  = @(
    "Show container status (local + remote)",
    "Logs: docker | app | errors | auth | db | files (+ level)",
    "Restart container on server",
    "Nginx reload (static dist deploy)",
    "Show remote config.json",
    "Rebuild image (compose) or dist folder (static)",
    "Stop container (keep on server)",
    "Start stopped container",
    "Stop + remove container (image + files stay)",
    "Full cleanup: container + image + server files",
    "Alias: undeploy",
    "Alias: delete"
)

# --- Help ---------------------------------------------------------
if ($Arg1 -in @("help","-h","--help")) {
    Write-Host ""
    Write-Host "  manage.ps1 - multi-package container management" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Usage:" -ForegroundColor White
    Write-Host "    .\manage.ps1                       interactive" -ForegroundColor Gray
    Write-Host "    .\manage.ps1 <package>             pick command interactively" -ForegroundColor Gray
    Write-Host "    .\manage.ps1 <command>             pick package interactively" -ForegroundColor Gray
    Write-Host "    .\manage.ps1 <command> <package>   direct (order doesn't matter)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  Commands:" -ForegroundColor White
    for ($i = 0; $i -lt $_validCommands.Count; $i++) {
        Write-Host ("    {0,-12} {1}" -f $_validCommands[$i], $_commandHints[$i]) -ForegroundColor Gray
    }
    Write-Host ""
    Write-Host "  Logs examples:" -ForegroundColor White
    Write-Host "    .\manage.ps1 logs errors" -ForegroundColor Gray
    Write-Host "    .\manage.ps1 logs app ERROR" -ForegroundColor Gray
    Write-Host ""
    exit 0
}

# --- Smart arg detection (order-independent) ----------------------
$Command = ""; $ServiceName = ""

function Normalize-Command {
    param([string]$c)
    switch ($c) { "rm" { "undeploy" } "nuke" { "delete" } default { $c } }
}
Resolve-ManageLogArgs -Arg1 $Arg1 -Arg2 $Arg2 -Arg3 $Arg3

function Test-ManageLogMetaArg {
    param([string]$Name)
    (Test-ManageLogSource $Name) -or ($Name -in @("ALL", "ERROR", "WARN", "INFO"))
}

if ($Arg1 -in $_validCommands -and $Arg2) {
    $Command = (Normalize-Command $Arg1)
    if ($Command -eq "logs" -and (Test-ManageLogMetaArg $Arg2)) { }
    else { $ServiceName = $Arg2 }
}
elseif ($Arg2 -in $_validCommands -and $Arg1) {
    $Command = (Normalize-Command $Arg2)
    if ($Command -eq "logs" -and (Test-ManageLogMetaArg $Arg1)) { }
    else { $ServiceName = $Arg1 }
}
elseif ($Arg1 -in $_validCommands) { $Command = (Normalize-Command $Arg1) }
elseif ($Arg1) { $ServiceName = $Arg1 }

# --- Package selection --------------------------------------------
$_services     = @(Get-ComposeServicesFromFile -ModuleRoot $ROOT -ComposeFile "docker-compose.yml")
$_serviceNames = @($_services | ForEach-Object { $_.Name })

if ($ServiceName) {
    if ($ServiceName -notin $_serviceNames) {
        Write-Host "  [ERROR] Service '$ServiceName' not found in docker-compose.yml." -ForegroundColor Red
        Write-Host "  Available: $($_serviceNames -join ', ')" -ForegroundColor Yellow
        exit 1
    }
} elseif ($_services.Count -eq 0) {
    Write-Host "  [ERROR] No services found in docker-compose.yml." -ForegroundColor Red
    exit 1
} elseif ($_services.Count -eq 1) {
    $ServiceName = $_services[0].Name
    Write-Host "  Auto-selected service: $ServiceName" -ForegroundColor DarkGray
} else {
    $ServiceName = Select-Option "Select Service" $_serviceNames ($_services | ForEach-Object { $_.Dockerfile })
}

Set-Service ($_services | Where-Object { $_.Name -eq $ServiceName })
if ($SERVER) {
    Update-DeployPathFromServer
}
if (-not $DEPLOY_PATH) {
    Set-DeployPathForMode -Kind "static"
}

# --- Command selection --------------------------------------------
if (-not $Command) {
    $Command = Select-Option "Select Command" $_validCommands $_commandHints
}

# --- Setup --------------------------------------------------------
$TIMESTAMP = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$LOG_FILE  = Join-Path $LOG_DIR "manage-${ServiceName}-${Command}_$TIMESTAMP.log"

$startTime   = Get-Date
$_serverHost = $SERVER -replace '^.*@', ''

# Remote commands require DEPLOY_SERVER
if ($Command -notin @("status")) {
    Assert-Env @("DEPLOY_SERVER")
}

function Get-RemoteDeployKind {
    if (-not $SERVER) { return "unknown" }
    $out = Invoke-SSHCapture @"
if [ -f '$DEPLOY_PATH/docker-compose.yml' ]; then echo compose
elif [ -f '$DEPLOY_PATH/dist/index.html' ]; then echo static
else echo unknown
fi
"@
    return ($out | Select-Object -Last 1).Trim()
}
$RemoteKind = if ($SERVER) { Get-RemoteDeployKind } else { "local" }

# ==================================================================
#  status - Show container status (local + remote)
# ==================================================================
if ($Command -eq "status") {
    LogBanner "$APP_NAME - Status" @{
        "Package" = $ServiceName
        "App"     = $APP_NAME
        "Server"  = if ($SERVER) { $SERVER } else { "(DEPLOY_SERVER not set)" }
        "Port"    = $HOST_PORT
    }

    # Local
    LogSection "Local Docker"
    $localStatus = docker inspect --format "{{.State.Status}}" $APP_NAME 2>$null
    if ($localStatus) {
        Log "Status: $localStatus" $(if ($localStatus -eq "running") { "OK" } else { "WARN" })
        docker ps --filter "name=$APP_NAME" --format "table {{.Names}}`t{{.Status}}`t{{.Ports}}" 2>&1 |
            ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
    } else {
        Log "No local container '$APP_NAME' found" "WARN"
    }

    # Remote (only if DEPLOY_SERVER is set)
    if ($SERVER) {
        LogSection "Remote Server ($_serverHost) [$RemoteKind]"
        $remoteScript = @"
echo '--- Container ---'
STATUS=`$(docker inspect --format '{{.State.Status}}' $APP_NAME 2>/dev/null || echo 'not found')
echo "  Status : `$STATUS"
echo ''
echo '--- Running ---'
docker ps --filter name=$APP_NAME --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null || echo '  (none)'
echo ''
echo '--- Image ---'
docker images $APP_NAME --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedSince}}' 2>/dev/null || echo '  (no image)'
echo ''
echo '--- Deploy dir ---'
du -sh $DEPLOY_PATH 2>/dev/null || echo '  (not found)'
if [ -f "$DEPLOY_PATH/dist/index.html" ]; then
  echo '  Mode   : static (dist + nginx)'
  [ -f "$DEPLOY_PATH/config.json" ] && echo '  Config : config.json present' || echo '  Config : config.json missing'
fi
if [ -f "$DEPLOY_PATH/docker-compose.yml" ]; then
  echo '  Mode   : remote compose (full source)'
fi
"@
        Invoke-SSH $remoteScript | Out-Null
    } else {
        Log "DEPLOY_SERVER not set - skipping remote status" "WARN"
    }
}

# ==================================================================
#  logs — docker | app | errors | auth | db | files (+ level filter)
# ==================================================================
elseif ($Command -eq "logs") {
    $logSource = Select-ManageLogSource
    $logLevel = ""
    if ($logSource -notin @("docker", "files")) {
        $logLevel = Select-ManageLogLevel
    }
    LogBanner "$APP_NAME - Logs ($logSource)" @{
        "Package"   = $ServiceName
        "Container" = $APP_NAME
        "Server"    = $SERVER
        "Level"     = if ($logLevel) { $logLevel } else { "ALL" }
        "Mode"      = $RemoteKind
    }
    Log "Connecting..." "STEP"
    Write-Host ""
    Invoke-ManageLogs -ContainerName $APP_NAME -DeployPath $DEPLOY_PATH `
        -LogSource $logSource -LogLevel $logLevel -RemoteKind $RemoteKind
    LogDone $startTime
}

# ==================================================================
#  restart - Restart container on server
# ==================================================================
elseif ($Command -eq "reload") {
    if ($RemoteKind -ne "static") {
        Log "reload is for static (dist/nginx) deploys; remote kind: $RemoteKind" "WARN"
    }
    Assert-Env @("DEPLOY_SERVER")
    $rc = Invoke-SSH "docker exec $APP_NAME nginx -s reload 2>/dev/null || docker restart $APP_NAME"
    if ($rc -ne 0) { exit 1 }
    Log "Nginx reloaded / container restarted" "OK"
    LogDone $startTime
}
elseif ($Command -eq "config") {
    Assert-Env @("DEPLOY_SERVER")
    Write-Host ""
    Invoke-SSHCapture "echo '--- config.json ---'; cat '$DEPLOY_PATH/dist/config.json' 2>/dev/null || echo '(not found)'"
    Invoke-SSHCapture "echo '--- .env.runtime.json ---'; cat '$DEPLOY_PATH/.env.runtime.json' 2>/dev/null || echo '(not found)'"
    $id = Get-KitIdentity
    Invoke-SSHCapture "echo '--- $($id.deployMarker) ---'; cat '$DEPLOY_PATH/$($id.deployMarker)' 2>/dev/null || cat '$DEPLOY_PATH/$($id.legacyDeployMarker)' 2>/dev/null || echo '(not found)'"
    Write-Host ""
    LogDone $startTime
}
elseif ($Command -eq "rebuild") {
    LogBanner "$APP_NAME - Rebuild" @{ "Mode" = $RemoteKind; "Server" = $SERVER }
    if ($RemoteKind -eq "static") {
        Log "Static deploy: run deploy.ps1 dist to rebuild" "WARN"
        LogDone $startTime
        exit 0
    }
    Assert-Env @("DEPLOY_SERVER")
    $rc = Invoke-SSH @"
set -euo pipefail
cd '$DEPLOY_PATH'
if docker compose version >/dev/null 2>&1; then DC='docker compose'; else DC=docker-compose; fi
`$DC -f docker-compose.yml --env-file ./.env.prod down 2>/dev/null || true
`$DC -f docker-compose.yml --env-file ./.env.prod build --no-cache
`$DC -f docker-compose.yml --env-file ./.env.prod up -d
docker ps --filter name=$APP_NAME
"@
    if ($rc -ne 0) { exit 1 }
    Log "Rebuild complete" "OK"
    LogDone $startTime
}
elseif ($Command -eq "restart") {
    LogBanner "$APP_NAME - Restart container" @{
        "Package"   = $ServiceName
        "Container" = $APP_NAME
        "Server"    = $SERVER
    }

    LogSection "Restarting container on server"
    $remoteScript = @"
set -euo pipefail
STATUS=`$(docker inspect --format '{{.State.Status}}' $APP_NAME 2>/dev/null || echo 'not found')
if [ "`$STATUS" = "not found" ]; then
  echo '[remote] Container not found - nothing to restart'
  exit 1
fi
echo "[remote] Current status: `$STATUS"
docker restart $APP_NAME
echo '[remote] Restarted OK'
docker ps --filter name=$APP_NAME
"@
    $rc = Invoke-SSH $remoteScript
    if ($rc -ne 0) { Log "Restart FAILED" "ERROR"; exit 1 }
    Log "Container restarted" "OK"
    LogDone $startTime
}

# ==================================================================
#  stop / start
# ==================================================================
elseif ($Command -eq "stop") {
    $rc = Invoke-SSH "docker stop $APP_NAME 2>/dev/null || echo '[remote] not running'"
    if ($rc -ne 0) { exit 1 }
    Log "Stopped $APP_NAME" "OK"
    LogDone $startTime
}
elseif ($Command -eq "start") {
    $rc = Invoke-SSH "docker start $APP_NAME && docker ps --filter name=$APP_NAME"
    if ($rc -ne 0) { Log "Start FAILED" "ERROR"; exit 1 }
    Log "Started $APP_NAME" "OK"
    LogDone $startTime
}

# ==================================================================
#  undeploy - Stop + remove container (image + server files stay)
# ==================================================================
elseif ($Command -eq "undeploy") {
    LogBanner "$APP_NAME - Undeploy" @{
        "Package"   = $ServiceName
        "Container" = $APP_NAME
        "Image"     = "stays"
        "Files"     = "stay at $DEPLOY_PATH"
    }

    Write-Host ""
    Write-Host "  This will STOP and REMOVE container '$APP_NAME' on $SERVER" -ForegroundColor Yellow
    Write-Host "  Docker image and server files will NOT be deleted." -ForegroundColor DarkGray
    Write-Host ""
    $confirm = Read-Host "  Continue? [y/N]"
    if ($confirm -notmatch "^[Yy]$") { Log "Cancelled by user" "WARN"; exit 0 }

    LogSection "Stop + remove container on server"
    $remoteScript = @"
set -euo pipefail
STATUS=`$(docker inspect --format '{{.State.Status}}' $APP_NAME 2>/dev/null || echo 'not found')
echo "[remote] Container '$APP_NAME': `$STATUS"
if [ "`$STATUS" = "not found" ]; then
  echo '[remote] Already undeployed'
  exit 0
fi
docker stop $APP_NAME
docker rm   $APP_NAME
echo '[remote] Done. Image and files remain on server.'
"@
    $rc = Invoke-SSH $remoteScript
    if ($rc -ne 0) { Log "Undeploy FAILED" "ERROR"; exit 1 }
    Log "Container stopped and removed" "OK"
    Log "Image and files still on server" "INFO"
    LogDone $startTime
}

# ==================================================================
#  delete - Full cleanup: container + image + server files [DESTRUCTIVE]
# ==================================================================
elseif ($Command -eq "delete") {
    LogBanner "$APP_NAME - DELETE (full cleanup)" @{
        "Package"   = $ServiceName
        "Container" = "$APP_NAME -> will be removed"
        "Image"     = "$APP_NAME -> will be removed"
        "Files"     = "$DEPLOY_PATH -> will be deleted"
    }

    Write-Host ""
    Write-Host "  ⚠  WARNING: This will permanently delete:" -ForegroundColor Red
    Write-Host "     • Container  : $APP_NAME" -ForegroundColor Red
    Write-Host "     • Image      : $APP_NAME" -ForegroundColor Red
    Write-Host "     • Server dir : $DEPLOY_PATH" -ForegroundColor Red
    Write-Host ""
    $confirm1 = Read-Host "  Are you sure? [y/N]"
    if ($confirm1 -notmatch "^[Yy]$") { Log "Cancelled" "WARN"; exit 0 }

    $confirm2 = Read-Host "  Type 'DELETE' to confirm"
    if ($confirm2 -ne "DELETE") { Log "Cancelled - did not type DELETE" "WARN"; exit 0 }
    Write-Host ""

    LogSection "Full cleanup on server"
    $remoteScript = @"
set -euo pipefail
echo '[remote] === Step 1: Stop container ==='
docker stop $APP_NAME 2>/dev/null && echo '[remote] Stopped' || echo '[remote] Not running'

echo '[remote] === Step 2: Remove container ==='
docker rm $APP_NAME 2>/dev/null && echo '[remote] Removed' || echo '[remote] Not found'

echo '[remote] === Step 3: Remove Docker image ==='
docker rmi $APP_NAME 2>/dev/null && echo '[remote] Image removed' || echo '[remote] Image not found'

echo '[remote] === Step 4: Delete server files ==='
if [ -d "$DEPLOY_PATH" ]; then
  rm -rf $DEPLOY_PATH
  echo '[remote] Deleted: $DEPLOY_PATH'
else
  echo '[remote] Directory not found: $DEPLOY_PATH'
fi

echo '[remote] === Verify ==='
docker ps -a --filter name=$APP_NAME | grep -q $APP_NAME && echo '[remote] WARN: container still exists' || echo '[remote] Container : clean'
docker images $APP_NAME | grep -q $APP_NAME              && echo '[remote] WARN: image still exists'     || echo '[remote] Image     : clean'
[ -d "$DEPLOY_PATH" ]                                    && echo '[remote] WARN: dir still exists'       || echo '[remote] Files     : clean'
"@
    $rc = Invoke-SSH $remoteScript
    if ($rc -ne 0) { Log "Delete FAILED (partial cleanup may have occurred)" "ERROR"; exit 1 }

    Log "Container removed" "OK"
    Log "Image removed" "OK"
    Log "Server files deleted: $DEPLOY_PATH" "OK"
    LogDone $startTime
}