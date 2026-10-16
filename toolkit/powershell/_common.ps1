# Portable ops toolkit (PowerShell) — dot-sourced via a PowerShell driver's _init.ps1
# Requires: $OpsScriptRoot (= module root), $OpsModuleRoot, $OpsSecretsModule, $OpsComposeFile

if (-not $OpsScriptRoot -or -not $OpsSecretsModule) {
    throw "Load the driver's _init.ps1 before the ops toolkit (_common.ps1)."
}

$ROOT = $OpsModuleRoot
. (Join-Path $PSScriptRoot "..\..\lib\project.ps1")
$LibEnv = Join-Path (Get-OpsPackageRoot) "lib\env.ps1"
if (-not (Test-Path $LibEnv)) {
    throw "stack-kit package lib/env.ps1 not found. Check stack-kit.json package path."
}
. $LibEnv
$SshLib = Join-Path (Get-OpsPackageRoot) "lib\ssh.ps1"
if (Test-Path $SshLib) { . $SshLib }

$MONOREPO    = Get-MonorepoRoot
$SECRETS_DIR = Get-SecretsModuleDir -Module $OpsSecretsModule
$LOG_DIR     = Join-Path $OpsScriptRoot "logs"
if (-not (Test-Path $LOG_DIR)) { New-Item -ItemType Directory -Path $LOG_DIR | Out-Null }

if (-not $OpsComposeFile) { $OpsComposeFile = "docker-compose.yml" }

function Get-EnvFileList {
    Get-SecretsEnvFiles -Module $OpsSecretsModule -Profile all
}

function Get-EnvValue {
    param([string]$Key, [string]$Default = $null)
    Get-SecretsEnvValue -Module $OpsSecretsModule -Key $Key -Default $Default
}

function Assert-Env {
    param([string[]]$Keys)
    $missing = $Keys | Where-Object { -not (Get-EnvValue $_) }
    if ($missing) {
        Write-Host ""
        foreach ($k in $missing) { Write-Host "  [ERROR] Missing env key: $k" -ForegroundColor Red }
        Write-Host "  Edit ops/config/$OpsSecretsModule/.env.* and ops/config/deploy.env" -ForegroundColor Yellow
        Write-Host ""
        exit 1
    }
}

$APP_NAME        = Split-Path $ROOT -Leaf
$DOCKERFILE_PATH = $null
$BUILD_CONTEXT   = $ROOT

$SERVER = Get-EnvValue "DEPLOY_SERVER"
if (-not $SERVER) { $SERVER = Get-DeployEnvValue "DEPLOY_SERVER" }
$script:ProjectSlug = Get-ProjectSlug
$script:SERVER_BASE = Get-EnvValue "DEPLOY_SERVER_BASE" (Get-DeployServerBase)
$SERVER_BASE = $script:SERVER_BASE
$script:DEPLOY_KIND = $null
$HOST_PORT   = Get-EnvValue "DEPLOY_HOST_PORT"   "80"
$DEPLOY_PATH = Get-EnvValue "DEPLOY_PATH"
if (-not $DEPLOY_PATH -and $SERVER_BASE) {
    $DEPLOY_PATH = "$SERVER_BASE/$ProjectSlug/$APP_NAME"
}

function Get-DockerServices {
    $composeFile = Join-Path $ROOT $OpsComposeFile
    if (-not (Test-Path $composeFile)) {
        Write-Host "  [ERROR] $OpsComposeFile not found in $ROOT" -ForegroundColor Red
        return @()
    }

    $lines    = Get-Content $composeFile
    $services = [System.Collections.ArrayList]@()
    $inSvc    = $false
    $inBuild  = $false
    $cur      = $null

    foreach ($line in $lines) {
        if ($line -match '^\s*#' -or $line -match '^\s*$') { continue }
        if ($line -match '^services\s*:') { $inSvc = $true; continue }
        if ($inSvc -and $line -match '^[a-zA-Z\-_]') { break }
        if (-not $inSvc) { continue }

        $indent  = ($line -replace '^(\s*).*', '$1').Length
        $trimmed = $line.Trim()

        if ($indent -eq 2 -and $trimmed -match '^([a-zA-Z0-9][a-zA-Z0-9_-]*)\s*:') {
            if ($cur) { [void]$services.Add($cur) }
            $cur = [PSCustomObject]@{
                Name          = $Matches[1]
                ContainerName = $Matches[1]
                Context       = '.'
                Dockerfile    = 'Dockerfile'
            }
            $inBuild = $false
            continue
        }

        if ($null -eq $cur) { continue }

        if ($indent -eq 4) {
            if ($trimmed -match '^container_name\s*:\s*(.+)') {
                $cur.ContainerName = $Matches[1].Trim().Trim('"').Trim("'")
            }
            if ($trimmed -match '^build\s*:\s*$')   { $inBuild = $true  }
            elseif ($trimmed -match '^[a-zA-Z]')    { $inBuild = $false }
        }

        if ($indent -eq 6 -and $inBuild) {
            if ($trimmed -match '^context\s*:\s*(.+)')    { $cur.Context    = $Matches[1].Trim().Trim('"').Trim("'") }
            if ($trimmed -match '^dockerfile\s*:\s*(.+)') { $cur.Dockerfile = $Matches[1].Trim().Trim('"').Trim("'") }
        }
    }

    if ($cur) { [void]$services.Add($cur) }
    return $services.ToArray()
}

function Select-Option {
    param(
        [string]  $Title,
        [string[]]$Options,
        [string[]]$Hints = @()
    )
    Write-Host ""
    Write-Host "  ------------------------------------------------------" -ForegroundColor DarkGray
    Write-Host "    $Title" -ForegroundColor Cyan
    Write-Host "  ------------------------------------------------------" -ForegroundColor DarkGray
    Write-Host ""
    for ($i = 0; $i -lt $Options.Count; $i++) {
        $hint = if ($i -lt $Hints.Count -and $Hints[$i]) { "  $($Hints[$i])" } else { "" }
        Write-Host ("    [{0}]  {1,-22}{2}" -f ($i + 1), $Options[$i], $hint) -ForegroundColor Gray
    }
    Write-Host ""
    $selected = $null
    do {
        $raw = Read-Host "    Enter number (1-$($Options.Count))"
        $n = 0
        if ([int]::TryParse($raw.Trim(), [ref]$n) -and $n -ge 1 -and $n -le $Options.Count) {
            $selected = $Options[$n - 1]
        } else {
            Write-Host "    Invalid. Enter a number between 1 and $($Options.Count)." -ForegroundColor Yellow
        }
    } while (-not $selected)
    Write-Host ""
    return $selected
}

function Set-Service {
    param([PSCustomObject]$Svc)

    $script:APP_NAME = $Svc.ContainerName

    if ($Svc.Context -eq '.' -or $Svc.Context -eq './') {
        $script:BUILD_CONTEXT = $ROOT
    } elseif ([IO.Path]::IsPathRooted($Svc.Context)) {
        $script:BUILD_CONTEXT = $Svc.Context
    } else {
        $script:BUILD_CONTEXT = Join-Path $ROOT $Svc.Context
    }

    if ([IO.Path]::IsPathRooted($Svc.Dockerfile)) {
        $script:DOCKERFILE_PATH = $Svc.Dockerfile
    } else {
        $script:DOCKERFILE_PATH = Join-Path $ROOT $Svc.Dockerfile
    }

    # DEPLOY_PATH set by Set-DeployPathForMode (Deploy-Path.ps1) after deploy mode is known
}

function Log {
    param(
        [string]$Message,
        [ValidateSet("INFO","STEP","OK","WARN","ERROR")]
        [string]$Level = "INFO"
    )
    $ts    = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $entry = "[$ts] [$Level] $Message"
    if ($LOG_FILE) { Add-Content -Path $LOG_FILE -Value $entry -Encoding UTF8 }
    $color = switch ($Level) {
        "STEP"  { "Cyan"   }
        "OK"    { "Green"  }
        "WARN"  { "Yellow" }
        "ERROR" { "Red"    }
        default { "Gray"   }
    }
    Write-Host $entry -ForegroundColor $color
}

function LogSection {
    param([string]$Title)
    Log "----------------------------------------------" "INFO"
    Log "  $Title" "STEP"
    Log "----------------------------------------------" "INFO"
}

function LogBanner {
    param([string]$Title, [hashtable]$Info = @{})
    Log "=======================================================" "INFO"
    Log "  $Title" "STEP"
    foreach ($key in $Info.Keys) {
        Log ("  {0,-14}: {1}" -f $key, $Info[$key]) "INFO"
    }
    Log "  Log           : $LOG_FILE" "INFO"
    Log "=======================================================" "INFO"
}

function LogDone {
    param([datetime]$StartTime)
    $secs = [math]::Round(((Get-Date) - $StartTime).TotalSeconds, 1)
    Log "=======================================================" "INFO"
    Log "  DONE in ${secs}s" "OK"
    Log "  Log  : $LOG_FILE" "INFO"
    Log "=======================================================" "INFO"
}

function Invoke-SSH {
    param([string]$Script)
    $sshExtra = @(Get-StackKitSshExtraArgs)
    ($Script -replace "`r", "") | & ssh @sshExtra $SERVER bash 2>&1 | ForEach-Object {
        if ($LOG_FILE) { Add-Content -Path $LOG_FILE -Value "[ssh] $_" -Encoding UTF8 }
        Write-Host "[ssh] $_" -ForegroundColor DarkGray
    }
    return $LASTEXITCODE
}

function Invoke-SSHCapture {
    param([string]$Script)
    $sshExtra = @(Get-StackKitSshExtraArgs)
    ($Script -replace "`r", "") | & ssh @sshExtra $SERVER bash 2>&1
}

function Invoke-SCP {
    param([string]$Source, [string]$Dest, [switch]$Recurse)
    $sshExtra = @(Get-StackKitSshExtraArgs)
    $scpArgs = @($sshExtra)
    if ($Recurse) { $scpArgs += "-r" }
    $scpArgs += $Source, "${SERVER}:${Dest}"
    & scp @scpArgs 2>&1 | ForEach-Object {
        if ($LOG_FILE) { Add-Content -Path $LOG_FILE -Value "[scp] $_" -Encoding UTF8 }
    }
    return $LASTEXITCODE
}
