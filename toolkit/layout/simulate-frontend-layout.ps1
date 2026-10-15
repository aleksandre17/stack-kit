# Frontend deploy layout simulation (dry-run, no SSH)
# Usage: stack-kit layout --frontend  |  simulate-frontend-layout.ps1 [-Json] [-Markdown]

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
if (-not $ModuleId) { $ModuleId = Get-ModuleIdByRole "ui" }
if (-not $ModuleId) { $ModuleId = (Get-ModuleIdsByDriverType "node-vite" | Select-Object -First 1) }
if (-not $ModuleId) { throw "manifest: no ui / node-vite module" }
$script:FeModuleId = $ModuleId
$script:FeSecretsFolder = Get-ModuleSecretsFolder $script:FeModuleId

function Get-DeployMeta {
    $server = Get-SecretsEnvValue -Module $script:FeSecretsFolder -Key "DEPLOY_SERVER"
    if (-not $server) { $server = Get-DeployEnvValue "DEPLOY_SERVER" }
    $project = Get-SecretsEnvValue -Module $script:FeSecretsFolder -Key "DEPLOY_PROJECT"
    if (-not $project) { $project = Get-DeployEnvValue "DEPLOY_PROJECT" }
    if (-not $project) { $project = Get-ProjectSlug }
    $base = Get-DeployServerBase
    $feDeployFromSecrets = Get-SecretsEnvValue -Module $script:FeSecretsFolder -Key "DEPLOY_PATH"
    $hostPort = Get-SecretsEnvValue -Module $script:FeSecretsFolder -Key "DEPLOY_HOST_PORT" -Default "5177"
    [PSCustomObject]@{
        Server           = $server
        Project          = $project
        ServerBase       = $base
        Network          = (Get-DockerNetworkName)
        DeployPathSecret = $feDeployFromSecrets
        HostPort         = $hostPort
    }
}

function Get-ComposeServicesFromYaml {
    param([string]$ComposePath)
    if (-not (Test-Path $ComposePath)) { return @() }
    $lines = Get-Content $ComposePath
    $inSvc = $false
    $cur = $null
    $list = [System.Collections.ArrayList]@()
    foreach ($line in $lines) {
        if ($line -match '^\s*#' -or $line -match '^\s*$') { continue }
        if ($line -match '^services\s*:') { $inSvc = $true; continue }
        if ($inSvc -and $line -match '^[a-zA-Z\-_]') { break }
        if (-not $inSvc) { continue }
        $indent = ($line -replace '^(\s*).*', '$1').Length
        $t = $line.Trim()
        if ($indent -eq 2 -and $t -match '^([a-zA-Z0-9][a-zA-Z0-9_-]*)\s*:') {
            if ($cur) { [void]$list.Add($cur) }
            $cur = [PSCustomObject]@{ Name = $Matches[1]; ContainerName = $Matches[1] }
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

function Get-SimEnvValue {
    param([string]$Key, [string]$Default = "")
    $fe = Get-SecretsModuleDir $script:FeSecretsFolder
    foreach ($name in @(".env.deploy", ".env.dev", ".env.prod")) {
        $p = Join-Path $fe $name
        if (-not (Test-Path $p)) { continue }
        foreach ($line in Get-Content $p) {
            if ($line -match '^\s*#' -or $line -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') { continue }
            if ($Matches[1] -eq $Key) { return $Matches[2].Trim().Trim('"').Trim("'") }
        }
    }
    return $Default
}

function Resolve-RemoteDeployPath {
    param([string]$ContainerName, [object]$Meta, [string]$Kind = "static")
    $base = $Meta.DeployPathSecret
    if (-not $base) { $base = Get-DefaultRemoteDeployPathBase -SecretsFolder $script:FeSecretsFolder }
    $base = $base.Trim().TrimEnd('/')
    $layout = Get-SimEnvValue "DEPLOY_LAYOUT" "structured"
    if ($layout -eq "structured") {
        switch ($Kind) {
            "static" { return "$base/static/$ContainerName" }
            "compose-dev" { return "$base/compose/dev/$ContainerName" }
            "compose-prod" { return "$base/compose/prod/$ContainerName" }
        }
    }
    if ($base -match "/$([regex]::Escape($ContainerName))$") { return $base }
    return "$base/$ContainerName"
}

function New-TreeNode {
    param([string]$Name, [object[]]$Children = @(), [string]$Note = "")
    [PSCustomObject]@{ Name = $Name; Children = @($Children); Note = $Note }
}

function Format-Tree {
    param([object]$Node, [string]$Prefix = "", [switch]$IsLast)
    if (-not $Node) { return @() }
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

function Get-RepoSecretsTree {
    param([string]$Repo)
    New-TreeNode (Join-Path $Repo "secrets") @(
        (New-TreeNode "deploy.env" -Note "DEPLOY_SERVER, DEPLOY_PROJECT"),
        (New-TreeNode "frontend/" @(
            (New-TreeNode ".env.deploy" -Note "DEPLOY_PATH, DEPLOY_LAYOUT, DEPLOY_HOST_PORT"),
            (New-TreeNode ".env.dev" -Note "VITE_API_URL, dev profile"),
            (New-TreeNode ".env.prod" -Note "prod profile"),
            (New-TreeNode "nginx.env" -Note "optional, nginx-gen")
        ))
    )
}

function Get-RepoFrontendSourceTree {
    param([string]$FeRoot)
    New-TreeNode $FeRoot @(
        (New-TreeNode "src/" @(
            (New-TreeNode "main.jsx"),
            (New-TreeNode "index.css"),
            (New-TreeNode "config/" @((New-TreeNode "api.js"))),
            (New-TreeNode "components/" @(
                (New-TreeNode "chatbot/" @(
                    (New-TreeNode "ChatWidget.jsx"),
                    (New-TreeNode "ChatMessage.jsx"),
                    (New-TreeNode "VoiceInputButton.jsx"),
                    (New-TreeNode "logo.svg")
                ))
            )),
            (New-TreeNode "hooks/" @((New-TreeNode "useChatTiers.jsx"))),
            (New-TreeNode "i18n/" @(
                (New-TreeNode "translations.js"),
                (New-TreeNode "LanguageContext.jsx")
            )),
            (New-TreeNode "Dockerfile" -Note "targets: deps, development, builder, production")
        )),
        (New-TreeNode "public/"),
        (New-TreeNode "package.json"),
        (New-TreeNode "package-lock.json"),
        (New-TreeNode "vite.config.js" -Note "if present"),
        (New-TreeNode "nginx.conf.template"),
        (New-TreeNode "nginx.conf" -Note "generated: stack-kit nginx-gen"),
        (New-TreeNode "docker-compose.yml" -Note "GENERATED"),
        (New-TreeNode "docker-compose.override.yml" -Note "dev: volume .:/app, develop.watch"),
        (New-TreeNode "docker-compose.prod.yml" -Note "prod overlay"),
        (New-TreeNode "ops.config.ps1"),
        (New-TreeNode "logs/" @(
            (New-TreeNode "deploy-*.log"),
            (New-TreeNode "watch-*.log"),
            (New-TreeNode "dev-*.log")
        ))
    )
}

function Get-StaticDistTree {
    New-TreeNode "dist/" @(
        (New-TreeNode "index.html"),
        (New-TreeNode "assets/" @(
            (New-TreeNode "index-[hash].js"),
            (New-TreeNode "index-[hash].css"),
            (New-TreeNode "..." -Note "chunks, fonts, images")
        )),
        (New-TreeNode "config.json" -Note "VITE_API_URL runtime")
    )
}

function Get-ServerStaticTree {
    param([string]$RemoteRoot)
    New-TreeNode $RemoteRoot @(
        (New-TreeNode ".stack-kit-deploy.json" -Note "manifest: kind=static, deployMode"),
        (New-TreeNode ".env.runtime.json" -Note "VITE_API_URL, environment, deployedAt"),
        (New-TreeNode "nginx.conf" -Note "from nginx-gen / module root"),
        (Get-StaticDistTree)
    )
}

function Get-ServerComposeDevTree {
    param([string]$RemoteRoot)
    New-TreeNode $RemoteRoot @(
        (New-TreeNode ".stack-kit-deploy.json" -Note "kind=compose-dev"),
        (New-TreeNode ".env.dev" -Note "merged secrets upload"),
        (New-TreeNode "docker-compose.yml"),
        (New-TreeNode "docker-compose.override.yml"),
        (New-TreeNode "package.json"),
        (New-TreeNode "package-lock.json"),
        (New-TreeNode "src/" @(
            (New-TreeNode "main.jsx"),
            (New-TreeNode "components/chatbot/..."),
            (New-TreeNode "Dockerfile")
        )),
        (New-TreeNode "public/"),
        (New-TreeNode "node_modules/" -Note "inside container volume, not rsynced from Windows")
    )
}

function Get-ServerStagingTree {
    param([string]$StagingDir, [string]$ArchiveName)
    New-TreeNode $StagingDir @(
        (New-TreeNode $ArchiveName -Note "tar.gz from deploy remote; removed after extract")
    )
}

$meta = Get-DeployMeta
$feRoot = Get-ManifestModulePath $script:FeModuleId
$beModId = Get-ModuleIdByRole "api"
if (-not $beModId) { $beModId = (Get-ModuleIdsByDriverType "java-boot" | Select-Object -First 1) }
$beRoot = if ($beModId) { Get-ManifestModulePath $beModId } else { $null }
$feRel = (Get-ManifestField "modules.$($script:FeModuleId).path") -replace '\\', '/'
$script:DeployEnvLbl = Get-DeployEnvPathLabel
$script:FeEnvDevLbl = (Get-ModuleEnvPathLabels $script:FeModuleId @('.env.dev'))[0]
$script:FeEnvProdLbl = (Get-ModuleEnvPathLabels $script:FeModuleId @('.env.prod'))[0]
$script:FeEnvDeployLbl = (Get-ModuleEnvPathLabels $script:FeModuleId @('.env.deploy'))[0]
$script:BeEnvDevLbl = if ($beModId) { (Get-ModuleEnvPathLabels $beModId @('.env.dev'))[0] } else { $null }
$svc = Get-ComposeServicesFromYaml (Join-Path $feRoot "docker-compose.yml")
if ($svc.Count -eq 0) {
    $svc = @([PSCustomObject]@{ Name = "app"; ContainerName = (Get-ComposeAppServiceName); Dockerfile = "src/Dockerfile"; Context = "." })
}
$container = $svc[0].ContainerName
$remoteStatic = Resolve-RemoteDeployPath -ContainerName $container -Meta $meta -Kind "static"
$remoteComposeDev = Resolve-RemoteDeployPath -ContainerName $container -Meta $meta -Kind "compose-dev"
$remoteComposeProd = Resolve-RemoteDeployPath -ContainerName $container -Meta $meta -Kind "compose-prod"
$stackDir = Get-StackComposeDirFromManifest
$localLogs = Join-Path $feRoot "logs"
$stagingDir = "$($meta.ServerBase)/$($meta.Project)/deploy-staging"
$legacyFlat = "$($meta.DeployPathSecret)/$container"
if (-not $meta.DeployPathSecret) {
    $feSeg = $script:FeSecretsFolder
    $legacyFlat = "$($meta.ServerBase)/$($meta.Project)/$feSeg/$container"
}

$scenarios = [ordered]@{}

# --- A. Local (no SSH) ---
$scenarios["A1-local-npm"] = [PSCustomObject]@{
    Id = "A1"
    Group = "Local (developer machine)"
    Title = "Vite dev server (host, no Docker)"
    Command = "cd $feRel && npm run dev"
    Host = "(localhost)"
    Root = $feRoot
    EnvFiles = @($script:FeEnvDevLbl)
    Docker = "none - Node on host :5173 (vite default) or vite.config"
    Runtime = "Hot reload; VITE_API_URL from .env.dev"
    Tree = New-TreeNode $RepoRoot @(
        (Get-RepoSecretsTree -Repo $RepoRoot),
        (Get-RepoFrontendSourceTree -FeRoot $feRoot),
        (New-TreeNode "node_modules/" -Note "local npm ci, not on server")
    )
    DockerStart = @(
        "1. (optional) cd frontend && npm ci",
        "2. npm run dev  →  vite --mode dev",
        "3. Browser → http://localhost:5173 (or configured port)"
    )
    DockerUpdate = @(
        "Save src/** → Vite HMR instant (no Docker, no stack-kit)"
    )
    Gaps = @("Port may differ from DEPLOY_HOST_PORT=5177 used in Docker modes.")
    Senior = @("Fastest inner loop when API is reachable from Windows.")
}

$scenarios["A2-local-compose-dev"] = [PSCustomObject]@{
    Id = "A2"
    Group = "Local (developer machine)"
    Title = "Docker compose - dev (module)"
    Command = ".\tools\stack-kit.ps1 fe compose up -d"
    Host = "(localhost)"
    Root = $feRoot
    EnvFiles = @($script:FeEnvDevLbl, $script:DeployEnvLbl)
    Docker = "image $container, target development, -p ${DEPLOY_HOST_PORT}:5177"
    Runtime = "Vite in container; compose develop.watch on ./src"
    Tree = New-TreeNode $feRoot @(
        (Get-RepoFrontendSourceTree -FeRoot $feRoot),
        (New-TreeNode "(Docker)" @(
            (New-TreeNode "container: $container"),
            (New-TreeNode "mount: $feRoot -> /app"),
            (New-TreeNode "mount: anonymous /app/node_modules"),
            (New-TreeNode "CMD: npm run dev -- --host 0.0.0.0")
        ))
    )
    DockerStart = @(
        "1. stack-kit compose-gen (if needed)",
        "2. cd frontend; docker compose -f docker-compose.yml -f docker-compose.override.yml up -d --build",
        "3. Container: development stage, port 5177:5177"
    )
    DockerUpdate = @(
        "Edit host frontend/src/** → volume reflects immediately",
        "compose develop.watch: sync src/ → /app/src in container",
        "package.json change → watch action rebuild image"
    )
    Gaps = @("GENERATED yaml - run stack-kit compose-gen after catalog change.")
    Senior = @("Parity test before D1 remote dev.")
}

$scenarios["A3-local-compose-prod"] = [PSCustomObject]@{
    Id = "A3"
    Group = "Local (developer machine)"
    Title = "Docker compose - prod overlay (local smoke)"
    Command = ".\tools\stack-kit.ps1 fe compose -Prod up -d --build"
    Host = "(localhost)"
    Root = $feRoot
    EnvFiles = @($script:FeEnvProdLbl, $script:DeployEnvLbl)
    Docker = "target production (nginx in image), build-arg VITE_API_URL"
    Runtime = "dist inside image at /usr/share/nginx/html"
    Tree = New-TreeNode $feRoot @(
        (New-TreeNode "docker-compose.yml"),
        (New-TreeNode "docker-compose.prod.yml"),
        (New-TreeNode "(image interior)" @(
            (New-TreeNode "usr/share/nginx/html/" @(
                (New-TreeNode "index.html"),
                (New-TreeNode "assets/...")
            )),
            (New-TreeNode "etc/nginx/conf.d/default.conf")
        ))
    )
    DockerStart = @(
        "1. docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build",
        "2. Stages: deps → builder (npm run build) → production (nginx)"
    )
    DockerUpdate = @(
        "Code change → must rebuild image (--build); no host dist/ sync"
    )
    Gaps = @("Not the same tree as B1 (host-built dist on server).")
    Senior = @("Smoke-test Dockerfile production stage.")
}

$scenarios["A4-local-stack"] = [PSCustomObject]@{
    Id = "A4"
    Group = "Local (developer machine)"
    Title = "Full stack - API + UI (stack compose)"
    Command = ".\tools\stack-kit.ps1 stack up -d --build"
    Host = "(localhost)"
    Root = $stackDir
    EnvFiles = @(
        $script:FeEnvDevLbl,
        $(if ($script:BeEnvDevLbl) { $script:BeEnvDevLbl }),
        $script:DeployEnvLbl
    ) | Where-Object { $_ }
    Docker = "ops/compose/stack/docker-compose.yml + manifest network"
    Runtime = "UI depends_on API health"
    Tree = New-TreeNode $RepoRoot @(
        (New-TreeNode (Get-ManifestField "stack.composeDir" "ops/compose/stack") @(
            (New-TreeNode "docker-compose.yml" -Note "build context from manifest modules"),
            (New-TreeNode "docker-compose.prod.yml")
        )),
        $(if ($beModId) {
            New-TreeNode (Get-ManifestField "modules.$beModId.path") @(
                (New-TreeNode "docker-compose.dev.yml"),
                (New-TreeNode "src/..."),
                (New-TreeNode "build/libs/*.jar")
            )
        }),
        (Get-RepoFrontendSourceTree -FeRoot $feRoot)
    )
    DockerStart = @(
        "1. stack-kit stack up -d --build",
        "2. Backend container(s) + frontend $container on shared network"
    )
    DockerUpdate = @(
        "Module rebuild via compose; not SSH module paths"
    )
    Gaps = @("Different roots than server static/compose trees.")
    Senior = @("Integration / E2E on laptop.")
}

$scenarios["A5-local-deploy-local"] = [PSCustomObject]@{
    Id = "A5"
    Group = "Local (developer machine)"
    Title = "deploy local - production image on laptop"
    Command = ".\tools\stack-kit.ps1 fe deploy local -Environment dev|prod"
    Host = "(localhost)"
    Root = $feRoot
    EnvFiles = @("$($script:FeSecretsFolder)/.env.{profile}", "VITE_API_URL, DEPLOY_HOST_PORT")
    Docker = "docker build --target production; docker run -p HOST_PORT:80"
    Runtime = "Container name = module folder leaf — may differ from compose service ($container)"
    Tree = New-TreeNode "(local Docker only)" @(
        (New-TreeNode "image: frontend" -Note "tag from folder name"),
        (New-TreeNode "container: frontend"),
        (New-TreeNode "port: DEPLOY_HOST_PORT:80"),
        (New-TreeNode $localLogs @(
            (New-TreeNode "deploy-*-local-*.log")
        ))
    )
    DockerStart = @(
        "1. stack-kit nginx-gen",
        "2. docker build --target production --build-arg VITE_API_URL=... -t frontend",
        "3. docker run -d --name frontend -p 5177:80 frontend"
    )
    DockerUpdate = @(
        "Re-run deploy local → stop/rm, rebuild image, run again"
    )
    Gaps = @("Container name differs from compose ($container).")
    Senior = @("Rare; use A2 or B1 instead.")
}

# --- B. Server static (dist) ---
$scenarios["B1-server-dist"] = [PSCustomObject]@{
    Id = "B1"
    Group = "Server - static (nginx + dist)"
    Title = "deploy dist (dev or prod profile)"
    Command = ".\tools\stack-kit.ps1 fe deploy dist -Environment dev|prod"
    Host = $meta.Server
    Root = $remoteStatic
    EnvFiles = @("$($script:FeSecretsFolder)/.env.{profile}", ".env.deploy", "server: .env.runtime.json")
    Docker = "nginx:1.27-alpine; volumes dist + nginx.conf; -p HOST_PORT:80"
    Runtime = "Static SPA; container $container"
    Tree = New-TreeNode $meta.Server @(
        (Get-ServerStagingTree -StagingDir $stagingDir -ArchiveName "(none for dist)"),
        (Get-ServerStaticTree -RemoteRoot $remoteStatic),
        (New-TreeNode "(Docker)" @(
            (New-TreeNode "container: $container"),
            (New-TreeNode "volume: $remoteStatic/dist -> /usr/share/nginx/html:ro"),
            (New-TreeNode "volume: $remoteStatic/nginx.conf -> /etc/nginx/conf.d/default.conf:ro")
        ))
    )
    DockerStart = @(
        "1. Windows: npm run build or build:dev (profile)",
        "2. Write frontend/dist/config.json",
        "3. scp -r dist/ + nginx.conf + .env.runtime.json -> $remoteStatic/",
        "4. ssh: docker stop/rm $container; docker run -d -p 5177:80 -v .../dist -v .../nginx.conf nginx:1.27-alpine"
    )
    DockerUpdate = @(
        "Full redeploy dist → rebuild npm, re-scp entire dist/, recreate container"
    )
    Gaps = @("Legacy flat path may exist: $legacyFlat")
    Senior = @("Default production/staging static UI on server.")
}

$scenarios["B2-server-sync"] = [PSCustomObject]@{
    Id = "B2"
    Group = "Server - static (nginx + dist)"
    Title = "deploy sync (+ nginx reload)"
    Command = ".\tools\stack-kit.ps1 fe deploy sync -Environment dev|prod"
    Host = $meta.Server
    Root = $remoteStatic
    EnvFiles = @("same as B1")
    Docker = "same container as B1; nginx -s reload or restart"
    Runtime = "Invoke-FeStaticPublishCycle: build + scp + reload"
    Tree = (Get-ServerStaticTree -RemoteRoot $remoteStatic)
    DockerStart = @("(assumes B1 container already running)")
    DockerUpdate = @(
        "1. Windows: npm build (profile)",
        "2. scp dist/, nginx.conf, .env.runtime.json",
        "3. ssh: docker exec $container nginx -s reload || docker restart"
    )
    Gaps = @()
    Senior = @("Quick prod-like UI patch without recreating container.")
}

$scenarios["B3-server-watch"] = [PSCustomObject]@{
    Id = "B3"
    Group = "Server - static (nginx + dist)"
    Title = "deploy watch - static dist loop (NOT dev watch)"
    Command = ".\tools\stack-kit.ps1 fe deploy watch -Environment dev|prod"
    Host = $meta.Server
    Root = $remoteStatic
    EnvFiles = @("same as B1")
    Docker = "same as B2 on each debounced save"
    Runtime = "FileSystemWatcher on src/ → repeat B2 cycle"
    Tree = New-TreeNode "Windows watch roots" @(
        (New-TreeNode (Join-Path $feRoot "src/") @(
            (New-TreeNode "components/chatbot/*.jsx"),
            (New-TreeNode "main.jsx")
        )),
        (New-TreeNode "→ npm build → scp -> $remoteStatic/dist/")
    )
    DockerStart = @("Requires prior B1 dist deploy (container up)")
    DockerUpdate = @("Each save (3s debounce): npm build + scp dist + nginx reload")
    Gaps = @("Heavy - use D2 for source-only remote dev.")
    Senior = @("Prod-like auto-publish from Windows.")
}

$scenarios["C1-server-remote-dev"] = [PSCustomObject]@{
    Id = "C1"
    Group = "Server - compose (full tar)"
    Title = "deploy remote dev (tar + server build)"
    Command = ".\tools\stack-kit.ps1 fe deploy remote -Environment dev"
    Host = $meta.Server
    Root = $remoteComposeDev
    EnvFiles = @("server: .env.dev (uploaded bundle)", "deploy.env")
    Docker = "compose up -d --build on server"
    Runtime = "Heavy; prefer D1 rsync for daily loop"
    Tree = New-TreeNode $meta.Server @(
        (Get-ServerStagingTree -StagingDir $stagingDir -ArchiveName "${container}_deploy_dev.tar.gz"),
        (Get-ServerComposeDevTree -RemoteRoot $remoteComposeDev)
    )
    DockerStart = @(
        "1. tar.gz frontend/ (excl node_modules, dist, .git)",
        "2. scp archive -> $stagingDir/",
        "3. ssh: tar -xzf -> $remoteComposeDev; scp .env.dev",
        "4. docker compose -f docker-compose.yml -f docker-compose.override.yml up -d --build"
    )
    DockerUpdate = @(
        "Each remote deploy: full archive again + --build (slow)"
    )
    Gaps = @("Large footprint; duplicates D1 path on repeat.")
    Senior = @("One-shot bootstrap alternative to D1 if rsync unavailable.")
}

$scenarios["D1-dev-bootstrap"] = [PSCustomObject]@{
    Id = "D1"
    Group = "Server - remote dev (SPA rsync)"
    Title = "dev bootstrap (rsync + compose up --build)"
    Command = ".\tools\stack-kit.ps1 fe dev bootstrap -Environment dev"
    Host = $meta.Server
    Root = $remoteComposeDev
    EnvFiles = @("server: .env.dev", $script:FeEnvDevLbl)
    Docker = "target development; -p 5177:5177; volume ${remoteComposeDev}:/app"
    Runtime = "npm run dev --host 0.0.0.0 in container"
    Tree = New-TreeNode $meta.Server @(
        (Get-ServerComposeDevTree -RemoteRoot $remoteComposeDev),
        (New-TreeNode "(Docker)" @(
            (New-TreeNode "container: $container"),
            (New-TreeNode "mount: $remoteComposeDev -> /app"),
            (New-TreeNode "develop.watch: src -> /app/src")
        ))
    )
    DockerStart = @(
        "1. rsync -avz --delete frontend/ -> $remoteComposeDev/ (excl node_modules, dist)",
        "2. Publish-RemoteEnvFiles -> .env.dev",
        "3. ssh cd $remoteComposeDev; docker compose up -d --build"
    )
    DockerUpdate = @(
        "Re-bootstrap after Dockerfile/package.json: fe dev bootstrap",
        "Daily edits: use D2/D3 instead (no --build)"
    )
    Gaps = @("Requires rsync (Git/WSL).")
    Senior = @("Best: Windows edit, Linux Vite in Docker.")
}

$scenarios["D2-dev-watch"] = [PSCustomObject]@{
    Id = "D2"
    Group = "Server - remote dev (SPA rsync)"
    Title = "dev watch (debounced rsync only)"
    Command = ".\tools\stack-kit.ps1 fe dev watch -Environment dev"
    Host = $meta.Server
    Root = $remoteComposeDev
    Docker = "container keeps running; Vite HMR + volume"
    Runtime = "No npm build; no docker restart on jsx/css"
    Tree = New-TreeNode "sync flow" @(
        (New-TreeNode $feRoot @(
            (New-TreeNode "src/components/chatbot/..."),
            (New-TreeNode "angular.json" -Note "Angular projects"),
            (New-TreeNode "projects/" -Note "Nx/monorepo UI")
        )),
        (New-TreeNode "rsync -> $remoteComposeDev"),
        (New-TreeNode "container Vite picks up /app changes")
    )
    DockerStart = @("After D1 bootstrap")
    DockerUpdate = @(
        "Save -> debounce 1.5s -> rsync delta only",
        "compose develop.watch may also sync src inside container"
    )
    Gaps = @()
    Senior = @("Primary inner loop for Windows->Linux UI dev.")
}

$scenarios["D3-dev-sync"] = [PSCustomObject]@{
    Id = "D3"
    Group = "Server - remote dev (SPA rsync)"
    Title = "dev sync (one-shot rsync)"
    Command = ".\tools\stack-kit.ps1 fe dev sync"
    Host = $meta.Server
    Root = $remoteComposeDev
    Docker = "no restart"
    Runtime = "Same rsync as D2 single shot"
    Tree = (Get-ServerComposeDevTree -RemoteRoot $remoteComposeDev)
    DockerStart = @()
    DockerUpdate = @("One rsync -avz --delete; container unchanged")
    Gaps = @()
    Senior = @("Manual push without watch process.")
}

$scenarios["D4-dev-restart"] = [PSCustomObject]@{
    Id = "D4"
    Group = "Server - remote dev (SPA rsync)"
    Title = "dev restart (compose restart)"
    Command = ".\tools\stack-kit.ps1 fe dev restart -Environment dev"
    Host = $meta.Server
    Root = $remoteComposeDev
    Docker = "docker compose restart (no rebuild)"
    Runtime = "After env change without full bootstrap"
    Tree = (Get-ServerComposeDevTree -RemoteRoot $remoteComposeDev)
    DockerStart = @()
    DockerUpdate = @("ssh: docker compose restart in $remoteComposeDev")
    Gaps = @()
    Senior = @("Lighter than bootstrap; no image rebuild.")
}

$scenarios["C2-server-remote-prod"] = [PSCustomObject]@{
    Id = "C2"
    Group = "Server - compose (full tar)"
    Title = "deploy remote prod"
    Command = ".\tools\stack-kit.ps1 fe deploy remote -Environment prod"
    Host = $meta.Server
    Root = $remoteComposeProd
    EnvFiles = @("server: .env.prod", "deploy.env")
    Docker = "compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build"
    Runtime = "production target in container on server"
    Tree = New-TreeNode $remoteComposeProd @(
        (New-TreeNode ".stack-kit-deploy.json"),
        (New-TreeNode ".env.prod"),
        (New-TreeNode "docker-compose.yml"),
        (New-TreeNode "docker-compose.prod.yml"),
        (New-TreeNode "src/"),
        (New-TreeNode "dist/" -Note "built inside image on server")
    )
    DockerStart = @("Same as C1 but path compose/prod/ and prod overlay")
    DockerUpdate = @("Full tar + --build each time")
    Gaps = @("Prefer B1 dist for production UI.")
    Senior = @("Optional server-side prod compose.")
}

$scenarios["E1-stack-deploy"] = [PSCustomObject]@{
    Id = "E1"
    Group = "Stack (backend + frontend)"
    Title = "stack-deploy (stack-kit.json steps)"
    Command = ".\tools\stack-kit.ps1 stack-deploy --prod"
    Host = $meta.Server
    Root = "$($meta.ServerBase)/$($meta.Project)"
    EnvFiles = @("backend secrets", "frontend .env.prod", "deploy.env")
    Docker = "be deploy all + fe deploy dist"
    Runtime = "B1 for UI + backend SSH deploy trees"
    Tree = New-TreeNode "$($meta.ServerBase)/$($meta.Project)" @(
        (New-TreeNode "backend/" @(
            (New-TreeNode "<service>/" @(
                (New-TreeNode "app.jar"),
                (New-TreeNode ".env.prod"),
                (New-TreeNode "docker-compose.prod.yml")
            ))
        )),
        (New-TreeNode "frontend/" @(
            (Get-ServerStaticTree -RemoteRoot $remoteStatic)
        )),
        (New-TreeNode "deploy-staging/")
    )
    DockerStart = @(
        "1. stack-kit be deploy all (backend modules)",
        "2. stack-kit fe deploy dist -Environment prod"
    )
    DockerUpdate = @("Re-run stack-deploy; not incremental")
    Gaps = @()
    Senior = @("Production full stack push.")
}

$scenarios["L0-legacy-flat"] = [PSCustomObject]@{
    Id = "L0"
    Group = "Legacy / migration"
    Title = "Flat layout (DEPLOY_LAYOUT=flat)"
    Command = "(old) deploy dist before structured paths"
    Host = $meta.Server
    Root = $legacyFlat
    EnvFiles = @(".env.deploy with DEPLOY_LAYOUT=flat")
    Docker = "same nginx pattern under flat path"
    Runtime = "Deprecated vs structured"
    Tree = New-TreeNode $legacyFlat @(
        (New-TreeNode "dist/"),
        (New-TreeNode "nginx.conf")
    )
    DockerStart = @("Same commands but Set-DeployPathForMode uses flat/{container}")
    DockerUpdate = @("Migrate to structured static/ after one B1 deploy")
    Gaps = @("Two paths may coexist until old dir removed.")
    Senior = @("Do not mix flat and structured on same host.")
}

# --- Summary / senior architecture ---
$scenarios["_summary"] = [PSCustomObject]@{
    Title = "Senior architecture  - target structure"
    Notes = @(
        "LOCAL: manifest module paths + ops/config + generated compose; logs under module logs/.",
        "SERVER STATIC (recommended prod): {base}/static/{service}/dist + nginx.conf  - no source, no node_modules.",
        "SERVER COMPOSE (dev/staging): {base}/compose/{service}/  - full source; isolate from static.",
        "PATH: clarify DEPLOY_PATH  - base directory OR full service path; avoid silent /{container_name} append.",
        "CI: npm build + optional dist layout dry-run; integration via stack not fe deploy.",
        "stack-deploy: uses dist (B1)  - align docs (GOLDEN-PATHS) with the chosen prod mode."
    )
    Matrix = @(
        [PSCustomObject]@{ Use = "Daily dev (local)"; Mode = "A1 / A2"; Server = "No"; Update = "HMR / compose watch" },
        [PSCustomObject]@{ Use = "Windows edit, Linux UI"; Mode = "D1 then D2"; Server = "Yes"; Update = "rsync only" },
        [PSCustomObject]@{ Use = "CI / build artifact"; Mode = "npm run build"; Server = "No"; Update = "N/A" },
        [PSCustomObject]@{ Use = "Prod UI (static)"; Mode = "B1 dist"; Server = "Yes"; Update = "B2 or B3" },
        [PSCustomObject]@{ Use = "Full stack prod"; Mode = "E1 stack-deploy"; Server = "Yes"; Update = "re-deploy" },
        [PSCustomObject]@{ Use = "Server compose UI"; Mode = "C1/C2 tar"; Server = "Yes"; Update = "full tar+build" },
        [PSCustomObject]@{ Use = "Legacy host"; Mode = "L0 flat"; Server = "Yes"; Update = "migrate to static/" }
    )
}

if ($Json) {
    $scenarios | ConvertTo-Json -Depth 14
    exit 0
}

if ($Markdown -or $OutFile) {
    $md = [System.Collections.ArrayList]@()
    [void]$md.Add("# Frontend deploy - full layout simulation")
    [void]$md.Add("")
    [void]$md.Add('> Dry-run from `ops/config` + `stack-kit.json`. Regenerate: stack-kit layout --frontend -Markdown -OutFile docs/FRONTEND-LAYOUT-SIMULATION-FULL.md')
    [void]$md.Add("")
    [void]$md.Add("## Resolved paths (this project)")
    [void]$md.Add("")
    [void]$md.Add("| Key | Path |")
    [void]$md.Add("|-----|------|")
    [void]$md.Add("| SSH | ``$($meta.Server)`` |")  # markdown backticks via format
    [void]$md.Add('| DEPLOY_PATH (base) | `' + $meta.DeployPathSecret + '` |')
    [void]$md.Add('| Static (B1/B2/B3) | `' + $remoteStatic + '` |')
    [void]$md.Add('| Compose dev (D/C1) | `' + $remoteComposeDev + '` |')
    [void]$md.Add('| Compose prod (C2) | `' + $remoteComposeProd + '` |')
    [void]$md.Add('| Staging archives | `' + $stagingDir + '` |')
    [void]$md.Add('| Legacy flat | `' + $legacyFlat + '` |')
    [void]$md.Add('| Local repo UI | `' + $feRoot + '` |')
    [void]$md.Add('| Container name | `' + $container + '` |')
    [void]$md.Add("")
    foreach ($key in $scenarios.Keys) {
        if ($key -eq "_summary") { continue }
        $s = $scenarios[$key]
        [void]$md.Add("---")
        [void]$md.Add("")
        [void]$md.Add("## $($s.Id) - $($s.Title)")
        [void]$md.Add("")
        [void]$md.Add("| | |")
        [void]$md.Add("|---|---|")
        [void]$md.Add('| Command | `' + $s.Command + '` |')
        [void]$md.Add("| Host | $($s.Host) |")
        [void]$md.Add('| Root | `' + $s.Root + '` |')
        [void]$md.Add("| Env | $($s.EnvFiles -join '; ') |")
        [void]$md.Add("| Docker | $($s.Docker) |")
        [void]$md.Add("| Runtime | $($s.Runtime) |")
        [void]$md.Add("")
        [void]$md.Add("### Directory tree")
        [void]$md.Add("")
        [void]$md.Add('```')
        Format-Tree -Node $s.Tree -IsLast | ForEach-Object { [void]$md.Add($_) }
        [void]$md.Add('```')
        [void]$md.Add("")
        if ($s.DockerStart) {
            [void]$md.Add("### Docker - start (bootstrap)")
            foreach ($line in $s.DockerStart) { [void]$md.Add("- $line") }
            [void]$md.Add("")
        }
        if ($s.DockerUpdate) {
            [void]$md.Add("### Docker - update (inner loop)")
            foreach ($line in $s.DockerUpdate) { [void]$md.Add("- $line") }
            [void]$md.Add("")
        }
        if ($s.Gaps.Count -gt 0) {
            [void]$md.Add("### Gaps / notes")
            foreach ($g in $s.Gaps) { [void]$md.Add("- $g") }
            [void]$md.Add("")
        }
        if ($s.Senior.Count -gt 0) {
            [void]$md.Add("### Recommendation")
            foreach ($r in $s.Senior) { [void]$md.Add("- $r") }
            [void]$md.Add("")
        }
    }
    [void]$md.Add("---")
    [void]$md.Add("")
    [void]$md.Add("## Architecture summary")
    foreach ($n in $scenarios["_summary"].Notes) { [void]$md.Add("- $n") }
    [void]$md.Add("")
    [void]$md.Add("| Use case | Mode | Server | Update mechanism |")
    [void]$md.Add("|----------|------|--------|------------------|")
    foreach ($row in $scenarios["_summary"].Matrix) {
        [void]$md.Add("| $($row.Use) | $($row.Mode) | $($row.Server) | $($row.Update) |")
    }
    $text = $md -join "`n"
    if ($OutFile) {
        $dest = if ([System.IO.Path]::IsPathRooted($OutFile)) { $OutFile } else { Join-Path $RepoRoot $OutFile }
        Set-Content -Path $dest -Value $text -Encoding UTF8
        Write-Host "  Wrote $dest" -ForegroundColor Green
    }
    if ($Markdown) { $text | Write-Output }
    exit 0
}

Write-Host ""
Write-Host "  Frontend deploy layout simulation (dry-run)" -ForegroundColor Cyan
Write-Host ('  SSH: ' + $meta.Server + '  |  project: ' + $meta.Project + '  |  base: ' + $meta.ServerBase) -ForegroundColor Gray
Write-Host "  DEPLOY_PATH (secrets): $($meta.DeployPathSecret)" -ForegroundColor Gray
Write-Host "  Static path:       $remoteStatic" -ForegroundColor White
Write-Host "  Compose dev path:  $remoteComposeDev" -ForegroundColor White
Write-Host "  Compose prod path: $remoteComposeProd" -ForegroundColor White
Write-Host "  Container / service:   $container" -ForegroundColor Gray
Write-Host ""

$lastGroup = ""
foreach ($key in $scenarios.Keys) {
    if ($key -eq "_summary") { continue }
    $s = $scenarios[$key]
    if ($s.Group -ne $lastGroup) {
        Write-Host "  ========== $($s.Group) ==========" -ForegroundColor Magenta
        $lastGroup = $s.Group
    }
    Write-Host ""
    Write-Host "  [$($s.Id)] $($s.Title)" -ForegroundColor Yellow
    Write-Host "  Command: $($s.Command)" -ForegroundColor Gray
    Write-Host "  Host:    $($s.Host)" -ForegroundColor Gray
    Write-Host "  Root:    $($s.Root)" -ForegroundColor White
    Write-Host "  Env:     $($s.EnvFiles -join ', ')" -ForegroundColor DarkGray
    Write-Host "  Docker:  $($s.Docker)" -ForegroundColor DarkGray
    Write-Host ""
    Format-Tree -Node $s.Tree -IsLast | ForEach-Object { Write-Host "  $_" }
    if ($s.DockerStart -and $s.DockerStart.Count -gt 0) {
        Write-Host ""
        Write-Host "  Docker START:" -ForegroundColor Cyan
        foreach ($line in $s.DockerStart) { Write-Host "    $line" -ForegroundColor DarkCyan }
    }
    if ($s.DockerUpdate -and $s.DockerUpdate.Count -gt 0) {
        Write-Host "  Docker UPDATE:" -ForegroundColor Cyan
        foreach ($line in $s.DockerUpdate) { Write-Host "    $line" -ForegroundColor DarkCyan }
    }
    if ($s.Gaps.Count -gt 0) {
        Write-Host ""
        Write-Host "  Gaps:" -ForegroundColor Red
        foreach ($g in $s.Gaps) { Write-Host "    - $g" -ForegroundColor $(if ($g -match '^HIGH') { "Red" } elseif ($g -match '^MED') { "Yellow" } else { "Gray" }) }
    }
    if ($s.Senior.Count -gt 0) {
        Write-Host "  Senior:" -ForegroundColor Green
        foreach ($r in $s.Senior) { Write-Host "    > $r" -ForegroundColor DarkGreen }
    }
}

Write-Host ""
Write-Host "  ========== Senior target ==========" -ForegroundColor Cyan
foreach ($n in $scenarios["_summary"].Notes) { Write-Host "  * $n" -ForegroundColor Gray }
Write-Host ""
Write-Host '  +-----------------------+-------------------+-----------+' -ForegroundColor DarkGray
Write-Host '  | Use case              | Mode              | On server |' -ForegroundColor DarkGray
Write-Host '  +-----------------------+-------------------+-----------+' -ForegroundColor DarkGray
foreach ($row in $scenarios["_summary"].Matrix) {
    Write-Host ('  | {0,-22} | {1,-17} | {2,-9} |' -f $row.Use, $row.Mode, $row.Server) -ForegroundColor Gray
}
Write-Host ""
Write-Host '  Full MD: stack-kit layout --frontend -Markdown -OutFile docs/FRONTEND-LAYOUT-SIMULATION-FULL.md' -ForegroundColor DarkGray
Write-Host '  Docs: docs/FRONTEND-DEPLOY-LAYOUTS.md' -ForegroundColor DarkGray
Write-Host ""
