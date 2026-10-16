# Backend deploy layout simulation (dry-run, no SSH)
# Usage: stack-kit layout --backend  |  -Markdown -OutFile docs/BACKEND-LAYOUT-SIMULATION-FULL.md

param(
    [string]$ModuleId = "",
    [switch]$Json,
    [switch]$Markdown,
    [string]$OutFile = ""
)

$ErrorActionPreference = "Stop"
$PackageRoot = $PSScriptRoot | Split-Path -Parent | Split-Path -Parent
. (Join-Path $PackageRoot "lib\project.ps1")
. (Join-Path $PackageRoot "lib\env.ps1")
. (Join-Path $PackageRoot "lib\modules.ps1")
$RepoRoot = Get-ProjectRootFromManifest
if (-not $RepoRoot) { throw "stack-kit.json not found" }
$env:STACK_KIT_PROJECT_ROOT = $RepoRoot
if (-not $ModuleId) { $ModuleId = Get-ModuleIdByRole "api" }
if (-not $ModuleId) { $ModuleId = (Get-ModuleIdsByLayoutSimulator "simulate-backend-layout.ps1" | Select-Object -First 1) }
if (-not $ModuleId) { throw "manifest: no api module, and no module whose driver declares this simulator" }
$script:BeModuleId = $ModuleId
$script:BeSecretsFolder = Get-ModuleSecretsFolder $script:BeModuleId

function Get-BeMeta {
    $server = Get-SecretsEnvValue -Module $script:BeSecretsFolder -Key "DEPLOY_SERVER"
    if (-not $server) { $server = Get-DeployEnvValue "DEPLOY_SERVER" }
    $project = Get-SecretsEnvValue -Module $script:BeSecretsFolder -Key "DEPLOY_PROJECT"
    if (-not $project) { $project = Get-DeployEnvValue "DEPLOY_PROJECT" }
    if (-not $project) { $project = Get-ProjectSlug }
    $base = Get-DeployServerBase
    $deployPath = Get-SecretsEnvValue -Module $script:BeSecretsFolder -Key "DEPLOY_PATH" -Default (Get-DefaultRemoteDeployPathBase -SecretsFolder $script:BeSecretsFolder)
    $layout = Get-SecretsEnvValue -Module $script:BeSecretsFolder -Key "DEPLOY_LAYOUT" -Default "flat"
    [PSCustomObject]@{
        Server     = $server
        Project    = $project
        ServerBase = $base
        DeployPath = $deployPath.TrimEnd('/')
        Layout     = $layout
        Network    = (Get-DockerNetworkName)
    }
}

function Get-ComposeServices {
    param([string]$ComposePath)
    if (-not (Test-Path $ComposePath)) { return @() }
    $lines = Get-Content $ComposePath
    $inSvc = $false; $cur = $null; $list = [System.Collections.ArrayList]@()
    foreach ($line in $lines) {
        if ($line -match '^\s*#' -or $line -match '^\s*$') { continue }
        if ($line -match '^services\s*:') { $inSvc = $true; continue }
        if ($inSvc -and $line -match '^[^ ]') { break }
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

function Resolve-BePath {
    param([object]$Meta, [string]$Container, [string]$Kind)
    if ($Meta.Layout -ne "structured") {
        return "$($Meta.DeployPath)/$Container"
    }
    switch ($Kind) {
        "runtime" { return "$($Meta.DeployPath)/runtime/$Container" }
        "workspace" { return "$($Meta.DeployPath)/workspace/$Container" }
        default { return "$($Meta.DeployPath)/$Container" }
    }
}

function Format-TreeLines {
    param([string[]]$Lines, [string]$Prefix = "")
    $out = [System.Collections.ArrayList]@()
    foreach ($line in $Lines) {
        [void]$out.Add("$Prefix$line")
    }
    return $out.ToArray()
}

$meta = Get-BeMeta
$beRoot = Get-ManifestModulePath $script:BeModuleId
$beDev = Get-ComposeServices (Join-Path $beRoot "docker-compose.dev.yml")
$beProd = Get-ComposeServices (Join-Path $beRoot "docker-compose.prod.yml")
$api = $beProd | Where-Object { $_.Service -match "api" } | Select-Object -First 1
if (-not $api) { $api = $beProd[0] }
$worker = $beProd | Where-Object { $_.Service -match "worker" } | Select-Object -First 1

$cname = $api.ContainerName
$runtimeApi = Resolve-BePath $meta $cname "runtime"
$workspaceApi = Resolve-BePath $meta $cname "workspace"
$flatLegacy = "$($meta.DeployPath)/$cname"

$scenarios = [ordered]@{}

$scenarios["L0-local"] = @{
    Id = "L0"
    Title = "Local dev (no SSH)"
    Command = "./gradlew bootRun  |  stack-kit be compose up --build"
    Host = "(localhost)"
    Root = $beRoot
    PathKind = "repo"
    Tree = @(
        "+-- backend/",
        "    |-- src/  (Spring Boot API)",
        "    |-- shared/",
        "    |-- worker/  (optional module)",
        "    |-- build.gradle.kts",
        "    +-- docker-compose.dev.yml  (local Docker)"
    )
    Notes = @("Golden path for daily dev on same machine as JVM.")
}

$scenarios["R1-deploy-dev"] = @{
    Id = "R1"
    Title = "be deploy --dev (JAR -> runtime/)"
    Command = "stack-kit be deploy $cname --dev"
    Host = $meta.Server
    Root = $runtimeApi
    PathKind = "runtime"
    Tree = @(
        "+-- $runtimeApi/",
        "    |-- Dockerfile  (from src/Dockerfile, COPY app.jar)",
        "    |-- app.jar  (built on Windows)",
        "    |-- .env.dev",
        "    |-- docker-compose.dev.yml  (generated on server)",
        "    |-- logs/",
        "    +-- info.log"
    )
    Notes = @("Structured layout requires $(Get-ModuleEnvPathLabels $script:BeModuleId @('.env.deploy')).")
}

$scenarios["R2-deploy-prod"] = @{
    Id = "R2"
    Title = "be deploy --prod (JAR + versions/)"
    Command = "stack-kit be deploy $cname --prod"
    Host = $meta.Server
    Root = $runtimeApi
    PathKind = "runtime"
    Tree = @(
        "+-- $runtimeApi/",
        "    |-- app.jar",
        "    |-- .env.prod",
        "    |-- docker-compose.prod.yml",
        "    |-- versions/app-*.jar",
        "    +-- logs/"
    )
    Notes = @("Rollback uses versions/ on failed healthcheck.")
}

$scenarios["R3-deploy-watch"] = @{
    Id = "R3"
    Title = "be deploy watch (Gradle loop -> runtime/)"
    Command = "stack-kit be deploy watch $cname --dev"
    Host = $meta.Server
    Root = $runtimeApi
    PathKind = "runtime"
    Tree = @(
        "Windows: src/, shared/, worker/  ->  gradlew bootJar",
        "  ->  scp app.jar  ->  $runtimeApi",
        "  ->  docker compose up --build"
    )
    Notes = @("Not be dev watch. Requires prior R1 deploy.")
}

$scenarios["W1-dev-bootstrap"] = @{
    Id = "W1"
    Title = "be dev bootstrap (rsync -> workspace/)"
    Command = "stack-kit be dev bootstrap $cname"
    Host = $meta.Server
    Root = $workspaceApi
    PathKind = "workspace"
    Tree = @(
        "+-- $workspaceApi/",
        "    |-- gradlew, build.gradle.kts, src/, shared/, worker/",
        "    |-- src/Dockerfile.dev.remote",
        "    |-- .env.dev, *credentials*.json (manifest credentials[])",
        "    |-- docker-compose.workspace.yml  (bootRun in container)",
        "    +-- volume .:/app + gradle cache"
    )
    Notes = @("DEPLOY_LAYOUT=structured required. Spring DevTools restarts on rsync.")
}

$scenarios["W2-dev-watch"] = @{
    Id = "W2"
    Title = "be dev watch (rsync only; DevTools reload)"
    Command = "stack-kit be dev watch $cname  # add --restart to force compose restart"
    Host = $meta.Server
    Root = $workspaceApi
    PathKind = "workspace"
    Tree = @(
        "Poll backend/src, shared/, worker/",
        "  →  rsync to $workspaceApi",
        "  →  DevTools triggers bootRun restart (default)",
        "  →  optional --restart for Dockerfile/gradle changes"
    )
    Notes = @()
}

if ($worker) {
    $wc = $worker.ContainerName
    $scenarios["R1-worker"] = @{
        Id = "R1w"
        Title = "be deploy worker --dev"
        Command = "stack-kit be deploy $($worker.Service) --dev"
        Host = $meta.Server
        Root = (Resolve-BePath $meta $wc "runtime")
        PathKind = "runtime"
        Tree = @("+-- $(Resolve-BePath $meta $wc 'runtime')/  (worker/Dockerfile, app.jar)")
        Notes = @()
    }
}

$scenarios["MIG-flat"] = @{
    Id = "MIG"
    Title = "Migration flat -> structured"
    Command = "bash kits/stack-kit/toolkit/deploy/migrate-backend-layout.sh --dry-run"
    Host = $meta.Server
    Root = $meta.DeployPath
    PathKind = "migrate"
    Tree = @(
        "Legacy: $flatLegacy",
        "  ->  mv to $runtimeApi",
        "New dev trees only under workspace/"
    )
    Notes = @("Run without --dry-run to apply on server.")
}

if ($Json) {
    $scenarios | ConvertTo-Json -Depth 8
    exit 0
}

$md = [System.Text.StringBuilder]::new()
[void]$md.AppendLine("# Backend deploy - full layout simulation")
[void]$md.AppendLine("")
[void]$md.AppendLine("> Dry-run from ``ops/config`` + ``stack-kit.json``. Regenerate: ``stack-kit layout --backend -Markdown -OutFile docs/BACKEND-LAYOUT-SIMULATION-FULL.md``")
[void]$md.AppendLine("")
[void]$md.AppendLine("## Resolved paths (this project)")
[void]$md.AppendLine("")
[void]$md.AppendLine("| Key | Value |")
[void]$md.AppendLine("|-----|-------|")
[void]$md.AppendLine("| SSH | ``$($meta.Server)`` |")
[void]$md.AppendLine("| DEPLOY_PATH | ``$($meta.DeployPath)`` |")
[void]$md.AppendLine("| DEPLOY_LAYOUT | ``$($meta.Layout)`` |")
[void]$md.AppendLine("| API runtime (R*) | ``$runtimeApi`` |")
[void]$md.AppendLine("| API workspace (W*) | ``$workspaceApi`` |")
[void]$md.AppendLine("| Legacy flat | ``$flatLegacy`` |")
[void]$md.AppendLine("| Local repo | ``$beRoot`` |")
[void]$md.AppendLine("| Container (API) | ``$cname`` |")
[void]$md.AppendLine("")
[void]$md.AppendLine("---")
[void]$md.AppendLine("")

foreach ($key in $scenarios.Keys) {
    $sc = $scenarios[$key]
    [void]$md.AppendLine("## $($sc.Id) - $($sc.Title)")
    [void]$md.AppendLine("")
    [void]$md.AppendLine("| | |")
    [void]$md.AppendLine("|---|---|")
    [void]$md.AppendLine("| Command | ``$($sc.Command)`` |")
    [void]$md.AppendLine("| Host | $($sc.Host) |")
    [void]$md.AppendLine("| Root | ``$($sc.Root)`` |")
    [void]$md.AppendLine("| Path kind | $($sc.PathKind) |")
    [void]$md.AppendLine("")
    [void]$md.AppendLine("### Directory tree / flow")
    [void]$md.AppendLine("")
    [void]$md.AppendLine("``````")
    foreach ($t in $sc.Tree) { [void]$md.AppendLine($t) }
    [void]$md.AppendLine("``````")
    [void]$md.AppendLine("")
    foreach ($n in $sc.Notes) {
        if ($n) { [void]$md.AppendLine("- $n") }
    }
    [void]$md.AppendLine("")
    [void]$md.AppendLine("---")
    [void]$md.AppendLine("")
}

$text = $md.ToString()

if ($Markdown -and $OutFile) {
    $outPath = if ([System.IO.Path]::IsPathRooted($OutFile)) { $OutFile } else { Join-Path $RepoRoot $OutFile }
    $dir = Split-Path $outPath -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    Set-Content -Path $outPath -Value $text -Encoding UTF8
    Write-Host "  Wrote $outPath" -ForegroundColor Green
}

Write-Host $text
