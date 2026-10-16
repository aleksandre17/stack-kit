# Env files, deploy values and naming for PowerShell -- a SHIM over lib/resolve_cli.py
# (ADR-001 decision 2).
#
# What the environment says changes during a run, so none of it is cached: each function asks the
# resolver, which holds the one rule -- which files a secrets folder reads and in what order, that a
# later file's value wins, that an operator's process environment beats deploy.env, how a slug is made.

. (Join-Path $PSScriptRoot "project.ps1")

function Get-Slugify {
    param([string]$Text)
    Invoke-KitResolver -Arguments @('slugify', $Text) | Select-Object -First 1
}

function Get-MonorepoRoot {
    $r = Get-KitContextValue 'monorepoRoot'
    if ($r) { return $r }
    throw "Project root not found ($((Get-KitIdentity).manifestFilename) required)"
}

function Get-SecretsRoot {
    Get-KitContextValue 'secretsRoot'
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
    @(Invoke-KitResolver -Arguments @('env-files', $Module, $Profile) | Where-Object { $_ })
}

function Get-SecretsEnvValue {
    # The last non-empty value of Key across the folder's env files, else Default.
    param([string]$Module, [string]$Key, [string]$Default = $null)
    $v = Invoke-KitResolver -Arguments @('env-value', $Module, $Key, $Default) | Select-Object -First 1
    if ($v) { return $v }
    return $Default
}

function Import-ModuleRunEnv {
    # A run's environment into this process: the folder's shared .env, then the one environment's
    # file over it (the resolver's rule, envfile.run_files). The values cross a pipe, never the console.
    param([Parameter(Mandatory = $true)][string]$Module, [ValidateSet("dev", "prod")][string]$Environment = "dev")
    $json = Invoke-KitResolver -Arguments @('run-env', $Module, $Environment) | Select-Object -First 1
    if (-not $json) { return }
    foreach ($p in ($json | ConvertFrom-Json).PSObject.Properties) {
        Set-Item -Path "env:$($p.Name)" -Value ([string]$p.Value)
    }
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
    # A shared deploy value: the process environment first, then deploy.env, else Default.
    param([string]$Key, [string]$Default = $null)
    $v = Invoke-KitResolver -Arguments @('deploy-env-value', $Key, $Default) | Select-Object -First 1
    if ($v) { return $v }
    return $Default
}

function Get-ProjectSlug {
    Invoke-KitResolver -Arguments @('project-slug') | Select-Object -First 1
}

function Get-ComposeSlug {
    Invoke-KitResolver -Arguments @('compose-slug') | Select-Object -First 1
}

function Get-DockerNetworkName {
    Invoke-KitResolver -Arguments @('docker-network') | Select-Object -First 1
}

function Get-DeployServerBase {
    $b = Invoke-KitResolver -Arguments @('server-base') | Select-Object -First 1
    if ($b) { return $b }
    return $null
}

function Get-InfraConsumerSlug {
    Invoke-KitResolver -Arguments @('infra-slug') | Select-Object -First 1
}

function Resolve-InfraDeployPath {
    Invoke-KitResolver -Arguments @('infra-deploy-path') | Select-Object -First 1
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
    $deployEnv = Get-DeployEnvFile
    if ((Test-Path $deployEnv) -and -not $seen[$deployEnv]) {
        [void]$args.Add("--env-file")
        [void]$args.Add($deployEnv)
    }
    return $args
}
