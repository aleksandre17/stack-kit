# Simulates remote directory layout after deploy (dry-run, no SSH).
# Usage: .\scripts\simulate-server-layout.ps1 [-Json]

param([switch]$Json)

$ErrorActionPreference = "Stop"
$PackageRoot = $PSScriptRoot | Split-Path -Parent | Split-Path -Parent
. (Join-Path $PackageRoot "lib\project.ps1")
. (Join-Path $PackageRoot "lib\env.ps1")
. (Join-Path $PackageRoot "lib\modules.ps1")
$RepoRoot = Get-ProjectRootFromManifest
if (-not $RepoRoot) { throw "stack-kit.json not found" }
$env:STACK_KIT_PROJECT_ROOT = $RepoRoot
$script:FeModuleId = Get-ModuleIdByRole "ui"
if (-not $script:FeModuleId) { $script:FeModuleId = (Get-ModuleIdsByDriverType "node-vite" | Select-Object -First 1) }
$script:BeModuleId = Get-ModuleIdByRole "api"
if (-not $script:BeModuleId) { $script:BeModuleId = (Get-ModuleIdsByDriverType "java-boot" | Select-Object -First 1) }
$script:FeSecretsFolder = if ($script:FeModuleId) { Get-ModuleSecretsFolder $script:FeModuleId } else { $null }
$script:BeSecretsFolder = if ($script:BeModuleId) { Get-ModuleSecretsFolder $script:BeModuleId } else { $null }

function Get-DeployMeta {
    $server = $null
    foreach ($folder in (Get-ListedSecretsModuleFolders)) {
        $server = Get-SecretsEnvValue -Module $folder -Key "DEPLOY_SERVER"
        if ($server) { break }
    }
    if (-not $server) { $server = Get-DeployEnvValue "DEPLOY_SERVER" }
    $project = $null
    foreach ($folder in (Get-ListedSecretsModuleFolders)) {
        $project = Get-SecretsEnvValue -Module $folder -Key "DEPLOY_PROJECT"
        if ($project) { break }
    }
    if (-not $project) { $project = Get-ProjectSlug }
    $base = Get-DeployServerBase
    [PSCustomObject]@{ Server = $server; Project = $project; ServerBase = $base; Network = (Get-DockerNetworkName) }
}

function Get-ComposeServices {
    param([string]$ComposePath)
    if (-not (Test-Path $ComposePath)) { return @() }
    $lines = Get-Content $ComposePath
    $inSvc = $false; $cur = $null; $list = [System.Collections.ArrayList]@()
    foreach ($line in $lines) {
        if ($line -match '^\s*#' -or $line -match '^\s*$') { continue }
        if ($line -match '^services\s*:') { $inSvc = $true; continue }
        if ($inSvc -and $line -match '^[a-zA-Z\-_]') { break }
        if (-not $inSvc) { continue }
        $indent = ($line -replace '^(\s*).*', '$1').Length
        $t = $line.Trim()
        if ($indent -eq 2 -and $t -match '^([a-zA-Z0-9][a-zA-Z0-9_-]*)\s*:') {
            if ($cur) { [void]$list.Add($cur) }
            $cur = [PSCustomObject]@{ Service = $Matches[1]; ContainerName = $Matches[1] }
            continue
        }
        if ($null -eq $cur) { continue }
        if ($indent -eq 4 -and $t -match '^container_name\s*:\s*(.+)') {
            $cur.ContainerName = $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
    if ($cur) { [void]$list.Add($cur) }
    return $list.ToArray()
}

function New-TreeNode {
    param([string]$Name, [object[]]$Children = @(), [string]$Note = "")
    [PSCustomObject]@{ Name = $Name; Children = @($Children); Note = $Note }
}

function Format-Tree {
    param([object]$Node, [string]$Prefix = "", [switch]$IsLast)
    $branch = if ($IsLast) { "+-- " } else { "|-- " }
    $cont = if ($IsLast) { "    " } else { "|   " }
    $note = if ($Node.Note) { "  # $($Node.Note)" } else { "" }
    $lines = @("$Prefix$branch$($Node.Name)$note")
    $kids = @($Node.Children)
    for ($i = 0; $i -lt $kids.Count; $i++) {
        $lines += Format-Tree -Node $kids[$i] -Prefix ($Prefix + $cont) -IsLast:($i -eq $kids.Count - 1)
    }
    return $lines
}

$meta = Get-DeployMeta
$feDeployBase = if ($script:FeSecretsFolder) {
    Get-SecretsEnvValue -Module $script:FeSecretsFolder -Key "DEPLOY_PATH" -Default (Get-DefaultRemoteDeployPathBase -SecretsFolder $script:FeSecretsFolder)
} else { $null }
$beDeployBase = if ($script:BeSecretsFolder) {
    Get-SecretsEnvValue -Module $script:BeSecretsFolder -Key "DEPLOY_PATH" -Default (Get-DefaultRemoteDeployPathBase -SecretsFolder $script:BeSecretsFolder)
} else { $null }
$beLayout = if ($script:BeSecretsFolder) {
    Get-SecretsEnvValue -Module $script:BeSecretsFolder -Key "DEPLOY_LAYOUT" -Default "structured"
} else { "structured" }

$beRoot = if ($script:BeModuleId) { Get-ManifestModulePath $script:BeModuleId } else { $null }
$feRoot = if ($script:FeModuleId) { Get-ManifestModulePath $script:FeModuleId } else { $null }
$beDevSvc = Get-ComposeServices (Join-Path $beRoot "docker-compose.dev.yml")
$beProdSvc = Get-ComposeServices (Join-Path $beRoot "docker-compose.prod.yml")
$feSvc = Get-ComposeServices (Join-Path $feRoot "docker-compose.yml")

$scenarios = [ordered]@{}

# --- Backend dev / prod (same tree shape, different env + compose file names) ---
foreach ($envName in @("dev", "prod")) {
    $svcList = if ($envName -eq "dev") { $beDevSvc } else { $beProdSvc }
    $envFile = ".env.$envName"
    $composeOnServer = "docker-compose.$envName.yml"
    $runtimeTrees = foreach ($s in $svcList) {
        $cname = $s.ContainerName
        $runtimePath = if ($beLayout -eq "structured") { "$beDeployBase/runtime/$cname" } else { "$beDeployBase/$cname" }
        $childNodes = @(
            (New-TreeNode "Dockerfile"),
            (New-TreeNode "app.jar"),
            (New-TreeNode $envFile),
            (New-TreeNode $composeOnServer -Note "generated on server from repo compose"),
            (New-TreeNode "*.p12, credentials*.json, ..." -Note "optional cred uploads"),
            (New-TreeNode "info.log"),
            (New-TreeNode "logs" @(
                (New-TreeNode "build.log"),
                (New-TreeNode "upload.log"),
                (New-TreeNode "compose.log"),
                (New-TreeNode "deploy.log")
            ))
        )
        if ($envName -eq "prod") {
            $childNodes += (New-TreeNode "versions" @(
                (New-TreeNode "app-YYYY-MM-DD_HH-mm-ss.jar" -Note "VERSIONS_KEEP snapshots")
            ))
        }
        New-TreeNode $runtimePath $childNodes -Note "compose service: $($s.Service); container: $cname"
    }
    $beRootNote = if ($beLayout -eq "structured") { "DEPLOY_LAYOUT=structured; workspace/ = be dev (bootRun)" } else { "DEPLOY_LAYOUT=flat (legacy)" }
    $scenarios["backend-deploy-watch-$envName"] = [PSCustomObject]@{
        Title = "Backend deploy watch - $envName (be deploy watch; Gradle loop to runtime/)"
        Host = $meta.Server
        Root = if ($beLayout -eq "structured") { "$beDeployBase/runtime" } else { $beDeployBase }
        Docker = "local gradlew bootJar -> scp app.jar -> compose up --build on server"
        Tree = if ($beLayout -eq "structured") {
            New-TreeNode "$beDeployBase/runtime" $runtimeTrees -Note "same tree as deploy; jar refreshed on save"
        } else {
            New-TreeNode $beDeployBase $runtimeTrees -Note "flat layout"
        }
    }

    $scenarios["backend-$envName"] = [PSCustomObject]@{
        Title = "Backend deploy - $envName (stack-kit be deploy --$envName)"
        Host = $meta.Server
        Root = $beDeployBase
        Docker = "docker compose -f docker-compose.$envName.yml --env-file ./.env.$envName up --build -d"
        Tree = if ($beLayout -eq "structured") {
            New-TreeNode $beDeployBase @(
                (New-TreeNode "runtime" $runtimeTrees -Note "JAR deploy")
                (New-TreeNode "workspace" @() -Note "be dev bootstrap / watch")
            ) -Note $beRootNote
        } else {
            New-TreeNode $beDeployBase $runtimeTrees -Note $beRootNote
        }
    }
}

# --- Frontend: per service + deploy mode ---
foreach ($s in $feSvc) {
    $cname = $s.ContainerName
    $svcPath = "$feDeployBase/$cname"

    $scenarios["frontend-dist-$cname"] = [PSCustomObject]@{
        Title = "Frontend deploy - dist/sync (deploy.ps1 dist|sync) - prod-like static"
        Host = $meta.Server
        Root = $svcPath
        Docker = "docker run nginx:1.27-alpine -v $svcPath/dist:/usr/share/nginx/html:ro -v $svcPath/nginx.conf:..."
        Tree = New-TreeNode $svcPath @(
            (New-TreeNode "dist" @(
                (New-TreeNode "index.html"),
                (New-TreeNode "assets/"),
                (New-TreeNode "..." -Note "npm run build output")
            )),
            (New-TreeNode "nginx.conf" -Note "from repo frontend/nginx.conf")
        ) -Note "no docker-compose on server; single nginx container"
    }

    $scenarios["frontend-remote-$cname"] = [PSCustomObject]@{
        Title = "Frontend deploy - remote (deploy.ps1 remote) - full source on server"
        Host = $meta.Server
        Root = $svcPath
        Docker = "docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build"
        Tree = New-TreeNode $svcPath @(
            (New-TreeNode "docker-compose.yml"),
            (New-TreeNode "docker-compose.prod.yml"),
            (New-TreeNode "nginx.conf"),
            (New-TreeNode "package.json"),
            (New-TreeNode "src/" -Note "Vite app sources"),
            (New-TreeNode "public/"),
            (New-TreeNode "dist/" -Note "created by build on server"),
            (New-TreeNode "node_modules/" -Note "after npm ci on server"),
            (New-TreeNode "..." -Note "tar extract of frontend/ minus node_modules,.git")
        ) -Note "archive dropped in $($meta.ServerBase)/ then extracted here"
    }

    $scenarios["frontend-local-$cname"] = [PSCustomObject]@{
        Title = "Frontend deploy - local (deploy.ps1 local) - NOT on server"
        Host = "(localhost)"
        Root = "N/A"
        Docker = "docker build + docker run on your machine only"
        Tree = New-TreeNode "(no remote files)" @() -Note "use for dev on laptop"
    }
}

# --- Dev vs prod mapping note ---
$scenarios["_note"] = [PSCustomObject]@{
    Title = "Dev vs prod mapping"
    Host = ""
    Root = ""
    Docker = ""
    Tree = $null
    Notes = @(
        "Backend: same folder layout; dev uses .env.dev + docker-compose.dev.yml, prod adds versions/ + rollback.",
        "Frontend: no --dev/--prod flag in deploy.ps1; dist=static prod UI, remote=compose prod overlay on server, local=laptop only.",
        "Full-stack dev/prod on one host is usually ops/compose/stack locally, not these per-module SSH trees."
    )
}

if ($Json) {
    $scenarios | ConvertTo-Json -Depth 12
    exit 0
}

Write-Host ""
Write-Host "  Server layout simulation (dry-run)" -ForegroundColor Cyan
Write-Host "  SSH target: $($meta.Server)" -ForegroundColor Gray
Write-Host "  Project:    $($meta.Project)  |  base: $($meta.ServerBase)" -ForegroundColor Gray
Write-Host ""

foreach ($key in $scenarios.Keys) {
    if ($key -eq "_note") { continue }
    $sc = $scenarios[$key]
    Write-Host "  =======================================================" -ForegroundColor DarkGray
    Write-Host "  $($sc.Title)" -ForegroundColor Yellow
    Write-Host "  Root: $($sc.Root)" -ForegroundColor White
    Write-Host "  Run:  $($sc.Docker)" -ForegroundColor DarkGray
    Write-Host ""
    Format-Tree -Node $sc.Tree -IsLast | ForEach-Object { Write-Host "  $_" }
    Write-Host ""
}

Write-Host "  -- Notes --" -ForegroundColor Cyan
foreach ($n in $scenarios["_note"].Notes) { Write-Host "  - $n" -ForegroundColor Gray }
Write-Host ""
