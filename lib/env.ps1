# stack-kit package — env & naming (no application logic)

. (Join-Path $PSScriptRoot "project.ps1")

function Get-Slugify {
    param([string]$Text)
    $s = $Text.ToLower() -replace '[^a-z0-9._-]+', '-'
    $s.Trim('-')
}

function Get-MonorepoRoot {
    if ($env:OPS_MONOREPO_ROOT) { return $env:OPS_MONOREPO_ROOT }
    if ($env:STACK_KIT_MONOREPO_ROOT) { return $env:STACK_KIT_MONOREPO_ROOT }
    if ($env:STACK_KIT_PROJECT_ROOT) { return $env:STACK_KIT_PROJECT_ROOT }
    $root = Get-ProjectRootFromManifest
    if ($root) { return $root }
    $dir = $PSScriptRoot
    if (-not $dir) { $dir = Split-Path -Parent $MyInvocation.MyCommand.Path }
    while ($dir) {
        if (Get-ManifestInDirectory $dir) { return $dir }
        if ($env:STACK_KIT_LEGACY_ROOT_DISCOVERY -match '^(1|true|yes|on)$') {
            if (Test-Path (Join-Path $dir "secrets")) { return $dir }
            if (Test-Path (Join-Path $dir "ops/config")) { return $dir }
        }
        $parent = Split-Path $dir -Parent
        if ($parent -eq $dir) { break }
        $dir = $parent
    }
    throw "Project root not found ($((Get-KitIdentity).manifestFilename) required; STACK_KIT_LEGACY_ROOT_DISCOVERY=1 for old trees)"
}

function Get-SecretsRoot {
    $root = Get-MonorepoRoot
    $rel = Get-ManifestField "secrets"
    Join-Path $root ($rel -replace '/', '\')
}

function Get-SecretsModuleDir {
    param([Parameter(Mandatory = $true)][string]$Module)
    Join-Path (Get-SecretsRoot) $Module
}

function Get-SecretsEnvFiles {
    param(
        [Parameter(Mandatory = $true)][string]$Module,
        [ValidateSet("dev", "prod", "deploy", "all")][string]$Profile = "all"
    )
    $dir = Get-SecretsModuleDir $Module
    $root = Get-MonorepoRoot
    $files = [System.Collections.ArrayList]@()

    if ($Profile -in @("dev", "all")) {
        $p = Join-Path $dir ".env.dev"
        if (Test-Path $p) { [void]$files.Add($p) }
    }
    if ($Profile -in @("prod", "all")) {
        $p = Join-Path $dir ".env.prod"
        if (Test-Path $p) { [void]$files.Add($p) }
    }
    if ($Profile -in @("deploy", "all")) {
        $shared = Join-Path (Get-SecretsRoot) "deploy.env"
        if (Test-Path $shared) { [void]$files.Add($shared) }
        $p = Join-Path $dir ".env.deploy"
        if (Test-Path $p) { [void]$files.Add($p) }
    }
    return $files
}

function Get-SecretsEnvValue {
    param([string]$Module, [string]$Key, [string]$Default = $null)
    $merged = @{}
    foreach ($file in (Get-SecretsEnvFiles -Module $Module -Profile "all")) {
        Get-Content $file | ForEach-Object {
            if ($_ -match '^\s*#' -or $_ -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') { return }
            $merged[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'")
        }
    }
    if ($merged.ContainsKey($Key) -and $merged[$Key]) { return $merged[$Key] }
    return $Default
}

function Get-ComposeEnvFileArgs {
    param(
        [Parameter(Mandatory = $true)][string]$Module,
        [ValidateSet("dev", "prod")][string]$Environment
    )
    $args = [System.Collections.ArrayList]@()
    foreach ($f in (Get-SecretsEnvFiles -Module $Module -Profile $Environment)) {
        [void]$args.Add("--env-file")
        [void]$args.Add($f)
    }
    return $args
}

function Get-DeployEnvFile {
    Join-Path (Get-SecretsRoot) "deploy.env"
}

function Get-DeployEnvValue {
    param([string]$Key, [string]$Default = $null)
    $fromEnv = [Environment]::GetEnvironmentVariable($Key)
    if ($fromEnv) { return $fromEnv }
    $file = Get-DeployEnvFile
    if (-not (Test-Path $file)) { return $Default }
    foreach ($line in Get-Content $file) {
        if ($line -match '^\s*#' -or $line -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') { continue }
        if ($Matches[1] -eq $Key) {
            $v = $Matches[2].Trim().Trim('"').Trim("'")
            if ($v) { return $v }
        }
    }
    return $Default
}

function Get-ProjectSlug {
    $slug = Get-DeployEnvValue "DEPLOY_PROJECT"
    if (-not $slug) { $slug = Split-Path (Get-MonorepoRoot) -Leaf }
    Get-Slugify $slug
}

function Get-ComposeSlug {
    $slug = Get-DeployEnvValue "COMPOSE_PROJECT_NAME"
    if (-not $slug) { $slug = Split-Path (Get-MonorepoRoot) -Leaf }
    Get-Slugify $slug
}

function Get-DockerNetworkName {
    $net = Get-DeployEnvValue "DOCKER_NETWORK"
    if (-not $net) { $net = Get-DeployEnvValue "STACK_KIT_DOCKER_NETWORK" }
    if (-not $net) { $net = "$(Get-ComposeSlug)-net" }
    $net
}

function Get-DeployServerBase {
    $base = Get-DeployEnvValue "DEPLOY_SERVER_BASE"
    if ($base) { return $base }
    foreach ($folder in (Get-ListedSecretsModuleFolders)) {
        $base = Get-SecretsEnvValue -Module $folder -Key "DEPLOY_SERVER_BASE"
        if ($base) { return $base }
    }
    $server = Get-DeployEnvValue "DEPLOY_SERVER"
    if (-not $server) {
        foreach ($folder in (Get-ListedSecretsModuleFolders)) {
            $server = Get-SecretsEnvValue -Module $folder -Key "DEPLOY_SERVER"
            if ($server) { break }
        }
    }
    if ($server -match '^([^@]+)@') { return "/home/$($Matches[1])" }
    return $null
}

function Get-InfraConsumerSlug {
    $s = Get-SecretsEnvValue -Module "infra" -Key "INFRA_SLUG"
    if ($s) { return (Get-Slugify $s.Trim()) }
    Get-Slugify (Split-Path (Get-MonorepoRoot) -Leaf)
}

function Resolve-InfraDeployPath {
    $explicit = Get-SecretsEnvValue -Module "infra" -Key "DEPLOY_PATH"
    $slug = Get-InfraConsumerSlug
    if ($explicit) {
        $base = $explicit.Trim().TrimEnd('/', '\').Replace("`r", "").Replace("`n", "")
        if ($base -notmatch "/infra/$([regex]::Escape($slug))$") {
            throw "DEPLOY_PATH must end with /infra/$slug (got: $base)"
        }
        return $base
    }
    $serverBase = Get-DeployServerBase
    $globalRoot = Get-DeployEnvValue "DEPLOY_PROJECT"
    if (-not $globalRoot) { $globalRoot = Get-ProjectSlug }
    if ($serverBase -and $globalRoot) {
        return "$serverBase/$(Get-Slugify $globalRoot)/infra/$slug"
    }
    return "/home/administrator/stack-kit/infra/$slug"
}

function Get-StackComposeEnvFileArgs {
    param([ValidateSet("dev", "prod")][string]$Environment)
    $args = [System.Collections.ArrayList]@()
    $seen = @{}
    foreach ($folder in (Get-ListedSecretsModuleFolders)) {
        foreach ($f in (Get-SecretsEnvFiles -Module $folder -Profile $Environment)) {
            if ($seen[$f]) { continue }
            $seen[$f] = $true
            [void]$args.Add("--env-file")
            [void]$args.Add($f)
        }
    }
    $deployEnv = Join-Path (Get-SecretsRoot) "deploy.env"
    if ((Test-Path $deployEnv) -and -not $seen[$deployEnv]) {
        [void]$args.Add("--env-file")
        [void]$args.Add($deployEnv)
    }
    return $args
}
