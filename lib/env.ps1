# Env files and run environments for PowerShell -- a SHIM over lib/resolve_cli.py
# (ADR-001 decision 2).
#
# What the environment says changes during a run, so none of it is cached: each function asks the
# resolver, which holds the one rule -- which files a secrets folder reads and in what order, that a
# later file's value wins, how a slug is made.

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
        [ValidateScript({ $_ -eq "all" -or (Test-KitEnvironment $_) })][string]$Profile = "all"
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
    # No environment: the catalog's run default (the resolver answers it, and refuses an undeclared one).
    param([Parameter(Mandatory = $true)][string]$Module, [string]$Environment = "")
    $json = Invoke-KitResolver -Arguments @('run-env', $Module, $Environment) | Select-Object -First 1
    if (-not $json) { return }
    foreach ($p in ($json | ConvertFrom-Json).PSObject.Properties) {
        Set-Item -Path "env:$($p.Name)" -Value ([string]$p.Value)
    }
}

function Get-ComposeEnvFileArgs {
    param(
        [Parameter(Mandatory = $true)][string]$Module,
        [ValidateScript({ Test-KitEnvironment $_ })][string]$Environment
    )
    $args = [System.Collections.ArrayList]@()
    foreach ($f in (Get-SecretsEnvFiles -Module $Module -Profile $Environment)) {
        [void]$args.Add("--env-file")
        [void]$args.Add($f)
    }
    return $args
}

