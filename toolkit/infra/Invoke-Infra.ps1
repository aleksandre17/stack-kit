# stack-kit — Postgres, Redis, Qdrant (local / remote / tunnel)
# Usage: stack-kit infra [prereqs|local|remote|tunnel] [up|down|sync|status|purge] [-Prod] [-Confirm]

param(
    [Parameter(Position = 0)]
    [string]$Mode = "help",
    [Parameter(Position = 1)]
    [string]$Action = "",
    [switch]$Prod,
    [switch]$Confirm
)

$ErrorActionPreference = "Stop"
$PackageRoot = if ($env:STACK_KIT_KIT_ROOT) {
    $env:STACK_KIT_KIT_ROOT
} else {
    (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

. (Join-Path $PackageRoot "lib\project.ps1")
. (Join-Path $PackageRoot "lib\env.ps1")
$SshLib = Join-Path $PackageRoot "lib\ssh.ps1"
if (Test-Path $SshLib) { . $SshLib }

$Root = Get-ProjectRootFromManifest
if (-not $Root) {
    Write-Host "[infra] stack-kit.json not found" -ForegroundColor Red
    exit 1
}
$env:STACK_KIT_PROJECT_ROOT = $Root

$InfraComposeDir = Get-InfraComposeDirFromManifest
$SecretsInfra = Join-Path (Get-SecretsRoot) "infra"

function Write-InfraLog {
    param([string]$Message, [string]$Level = "INFO")
    $color = switch ($Level) {
        "ERROR" { "Red" }
        "WARN" { "Yellow" }
        default { "Cyan" }
    }
    Write-Host "[infra] $Message" -ForegroundColor $color
}

function Resolve-InfraEnvFile {
    if ($Prod) {
        $f = Join-Path $SecretsInfra ".env.prod"
        if (-not (Test-Path $f)) { $f = Join-Path $SecretsInfra ".env.dev" }
        return $f
    }
    return Join-Path $SecretsInfra ".env.dev"
}

function Assert-InfraEnvFile {
    $f = Resolve-InfraEnvFile
    if (-not (Test-Path $f)) {
        Write-InfraLog "Missing $f - copy from ops/config/infra/.env.example" "ERROR"
        exit 1
    }
    return $f
}

function Resolve-InfraComposeFileArgs {
    param([bool]$IsProd)
    try {
        $null = Get-InfraComposeIncludeFiles
    }
    catch {
        Write-InfraLog $_.Exception.Message "ERROR"
        exit 1
    }
    $files = [System.Collections.ArrayList]@()
    Add-InfraComposeFileArgs -Target $files
    if ($IsProd) {
        $prod = Join-Path $InfraComposeDir "docker-compose.prod.yml"
        if (Test-Path $prod) { [void]$files.AddRange(@('-f', $prod)) }
        $coexist = Join-Path $InfraComposeDir "docker-compose.coexist.yml"
        if (Test-Path $coexist) { [void]$files.AddRange(@('-f', $coexist)) }
    }
    return $files.ToArray()
}

function Invoke-InfraLocalCompose {
    param([string]$ComposeAction)
    $envFile = Assert-InfraEnvFile
    $composeArgs = Resolve-InfraComposeFileArgs -IsProd $Prod
    Push-Location $InfraComposeDir
    try {
        $cmd = @('compose') + $composeArgs + @('--env-file', $envFile, $ComposeAction)
        Write-InfraLog "docker $($cmd -join ' ')"
        & docker @cmd
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    finally {
        Pop-Location
    }
}

function Get-InfraRemotePaths {
    $remoteBase = (Resolve-InfraDeployPath -replace '\\', '/').TrimEnd('/')
    return @{
        Base    = $remoteBase
        Compose = "$remoteBase/compose"
        Env     = "$remoteBase/.env.runtime"
    }
}

function Upload-InfraToRemote {
    $server = Get-DeployEnvValue "DEPLOY_SERVER"
    if (-not $server) {
        Write-InfraLog "Set DEPLOY_SERVER in ops/config/deploy.env" "ERROR"
        exit 1
    }
    $paths = Get-InfraRemotePaths
    $remoteBase = $paths.Base
    $remoteCompose = $paths.Compose
    $slug = Get-InfraConsumerSlug
    Write-InfraLog "Sync -> ${server}:$remoteCompose (slug=$slug)"

    if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
        Write-InfraLog "ssh not found" "ERROR"
        exit 1
    }
    $mkdirRc = Invoke-StackKitRemoteBash "mkdir -p '$remoteCompose'"
    if ($mkdirRc -ne 0) {
        Write-InfraLog "mkdir on server failed (exit $mkdirRc)" "ERROR"
        exit 1
    }

    $rsync = Get-Command rsync -ErrorAction SilentlyContinue
    if ($rsync) {
        $src = ($InfraComposeDir -replace "\\", "/") + "/"
        $dest = "${server}:$remoteCompose/"
        $excludes = @('--exclude', '.git', '--exclude', 'ps1', '--exclude', 'sh', '--exclude', 'logs')
        & rsync -avz --delete $excludes $src $dest
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    else {
        Write-InfraLog "rsync not found - using scp" "WARN"
        foreach ($rel in (Get-InfraSyncRelativePaths)) {
            $local = Join-Path $InfraComposeDir ($rel -replace '/', '\')
            if (-not (Test-Path $local)) { continue }
            $remoteFile = "$remoteCompose/" + ($rel -replace '\\', '/')
            $remoteDir = ($remoteFile -replace '\\', '/')
            if ($remoteDir -match '/') {
                $parent = $remoteDir.Substring(0, $remoteDir.LastIndexOf('/'))
                if ($parent) {
                    $null = Invoke-StackKitRemoteBash "mkdir -p '$parent'"
                }
            }
            $scpRc = Invoke-StackKitScp $local $remoteFile
            if ($scpRc -ne 0) { exit $scpRc }
        }
    }

    $envFile = Assert-InfraEnvFile
    $remoteEnv = "$remoteBase/.env.runtime"
    $scpRc = Invoke-StackKitScp $envFile $remoteEnv
    if ($scpRc -ne 0) { exit $scpRc }
    Write-InfraLog "Synced compose + .env.runtime"
}

function Invoke-InfraRemoteCompose {
    param([string]$ComposeAction)
    $server = Get-DeployEnvValue "DEPLOY_SERVER"
    if (-not $server) {
        Write-InfraLog "Set DEPLOY_SERVER in ops/config/deploy.env" "ERROR"
        exit 1
    }
    $paths = Get-InfraRemotePaths
    $remoteBase = $paths.Base
    $remoteCompose = $paths.Compose
    $envRemote = $paths.Env
    $composeParts = [System.Collections.ArrayList]@()
    Add-InfraComposeFileArgs -Target $composeParts
    $composeFiles = (($composeParts -join ' ') -replace '\\', '/')
    if ($Prod) { $composeFiles += " -f docker-compose.prod.yml" }
    $coexist = Join-Path $InfraComposeDir "docker-compose.coexist.yml"
    if ($Prod -and (Test-Path $coexist)) { $composeFiles += " -f docker-compose.coexist.yml" }
    $prodFlag = if ($Prod) { " (prod overlay)" } else { "" }
    Write-InfraLog "Remote $ComposeAction on $server$prodFlag -> $remoteBase"

    $remoteScript = (
        'set -euo pipefail; cd "{0}"; ' +
        'if docker compose version >/dev/null 2>&1; then docker compose {1} --env-file "{2}" {3}; ' +
        'else docker-compose {1} --env-file "{2}" {3}; fi'
    ) -f $remoteCompose, $composeFiles, $envRemote, $ComposeAction
    $sshRc = Invoke-StackKitRemoteBash $remoteScript
    if ($sshRc -ne 0) { exit $sshRc }
}

function Invoke-InfraRemotePurge {
    if (-not $Confirm) {
        Write-InfraLog "remote purge removes THIS project containers and volumes only. Pass -Confirm." "ERROR"
        exit 1
    }
    $remoteBase = (Get-InfraRemotePaths).Base
    $slug = Get-InfraConsumerSlug
    if ($remoteBase -notmatch "/infra/$([regex]::Escape($slug))`$") {
        Write-InfraLog "Refusing purge: path must end with /infra/$slug (got $remoteBase)" "ERROR"
        exit 1
    }
    Write-InfraLog "Purge infra stack at $remoteBase (other projects under .../infra/ are untouched)" "WARN"
    Invoke-InfraRemoteCompose "down -v --remove-orphans"
}

function Start-InfraTunnel {
    $server = Get-DeployEnvValue "DEPLOY_SERVER"
    if (-not $server) {
        Write-InfraLog "Set DEPLOY_SERVER in ops/config/deploy.env" "ERROR"
        exit 1
    }
    try {
        $forwards = Get-InfraTunnelForwards
    }
    catch {
        Write-InfraLog $_.Exception.Message "ERROR"
        exit 1
    }
    $sshExtra = @(Get-StackKitSshExtraArgs)
    $portList = ($forwards | ForEach-Object { $_.Local }) -join ','
    $svcList = ($forwards | ForEach-Object { "$($_.Service)($($_.Env))" }) -join ', '
    Write-InfraLog "SSH tunnel (Ctrl+C) services: $svcList"
    Write-InfraLog "localhost ports -> ${server}: $portList"
    Write-InfraLog "Set INFRA_HOST=127.0.0.1 in app .env.dev (hybrid)"
    $sshArgs = [System.Collections.ArrayList]@()
    $sshArgs.AddRange($sshExtra)
    [void]$sshArgs.Add('-N')
    foreach ($f in $forwards) {
        [void]$sshArgs.Add('-L')
        [void]$sshArgs.Add("$($f.Local):127.0.0.1:$($f.Remote)")
    }
    [void]$sshArgs.Add($server)
    & ssh @sshArgs
}

function Show-InfraHelp {
    Write-Host @"

  stack-kit infra - Postgres, Redis, Qdrant (stack-kit)

    prereqs              SSH: docker network + checks
    local up|down|status Docker on this machine
    remote sync          Upload compose + .env.runtime (scoped to infra/<INFRA_SLUG>/)
    remote up|down|status
    remote purge -Confirm  down -v for THIS slug only (not sibling projects)
    tunnel               ssh -L (ports from stack.infra.services + infra-catalog)

    -Prod                .env.prod + docker-compose.prod.yml overlay

  Compose dir: stack.infraComposeDir in stack-kit.json
  Remote path: {DEPLOY_SERVER_BASE}/{DEPLOY_PROJECT}/infra/{INFRA_SLUG}

"@
}

$bash = Get-Command bash -ErrorAction SilentlyContinue
switch ($Mode.ToLowerInvariant()) {
    "help" { Show-InfraHelp; exit 0 }
    "prereqs" {
        if (-not $bash) { Write-InfraLog "Git Bash required for prereqs" "ERROR"; exit 1 }
        & $bash (Join-Path $PackageRoot "toolkit\infra\ensure-prereqs.sh")
        exit $LASTEXITCODE
    }
    "local" {
        switch ($Action.ToLowerInvariant()) {
            "up" { Invoke-InfraLocalCompose "up -d" }
            "down" { Invoke-InfraLocalCompose "down" }
            "status" { Invoke-InfraLocalCompose "ps" }
            default { Write-InfraLog "Usage: stack-kit infra local up|down|status" "ERROR"; exit 1 }
        }
    }
    "remote" {
        switch ($Action.ToLowerInvariant()) {
            "sync" { Upload-InfraToRemote }
            "up" {
                Upload-InfraToRemote
                Invoke-InfraRemoteCompose "up -d --remove-orphans"
            }
            "down" { Invoke-InfraRemoteCompose "down" }
            "status" { Invoke-InfraRemoteCompose "ps" }
            "purge" { Invoke-InfraRemotePurge }
            default { Write-InfraLog "Usage: stack-kit infra remote up|down|sync|status|purge -Confirm" "ERROR"; exit 1 }
        }
    }
    "tunnel" { Start-InfraTunnel }
    default {
        Write-InfraLog "Unknown mode: $Mode" "ERROR"
        Show-InfraHelp
        exit 1
    }
}
