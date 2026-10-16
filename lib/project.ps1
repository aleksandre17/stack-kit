# Project resolution for PowerShell -- a SHIM over lib/resolve_cli.py (ADR-001 decision 2).
#
# This file holds no rule. Which directory is the project, which manifest name is read, what a
# field defaults to, which module has which role, which compose files make the infra stack: the
# resolver answers. What the MANIFEST says is resolved once per (declared root, else working
# directory) as one map of `kind:key` -> text and kept for the session; what the ENVIRONMENT says
# is asked each time. A test holds this: no manifest field is spelled here.

. (Join-Path $PSScriptRoot "stack-kit-python.ps1")

# Dot-sourced again by drivers.ps1, modules.ps1 and env.ps1: keep what an earlier load resolved.
foreach ($name in @('KitIdentity', 'KitContext', 'KitContextKey', 'KitPython')) {
    if (-not (Get-Variable -Name $name -Scope Script -ErrorAction SilentlyContinue)) {
        Set-Variable -Name $name -Scope Script -Value $null
    }
}

function Test-KitEnvironment {
    # True for an environment the catalog declares (config/catalogs/environments.json, or the host's
    # own entries); else refused, naming the declared ones. The one PowerShell check of it.
    param([string]$Name)
    $declared = @(Get-KitContextLines 'environments')
    if ($declared -contains $Name) { return $true }
    throw "'$Name' is not a declared environment ($($declared -join ', ')); a host adds one to its manifest's environment catalog"
}

function Get-KitIdentity {
    # The declaration itself, read as data: names, not rules.
    if ($null -ne $script:KitIdentity) { return $script:KitIdentity }
    $decl = Join-Path $PSScriptRoot 'identity.json'
    if (-not (Test-Path $decl)) { throw "kit identity declaration missing: $decl" }
    $script:KitIdentity = Get-Content -Raw -Encoding UTF8 $decl | ConvertFrom-Json
    return $script:KitIdentity
}

function Invoke-KitResolver {
    # The resolver's answer as lines. Its stderr (a deprecation notice, an error) is passed through
    # unless -Quiet; a failure throws with the resolver's words, or returns $null when -Optional.
    param(
        [Parameter(Mandatory = $true)][AllowEmptyString()][string[]]$Arguments,
        [switch]$Optional,
        [switch]$Quiet
    )
    if (-not $script:KitPython) {
        $script:KitPython = Get-StackKitPythonArgs
        if (-not $script:KitPython) { throw "Python not found (tried py -3, python3, python)" }
    }
    $cli = Join-Path $PSScriptRoot 'resolve_cli.py'
    $exe = $script:KitPython[0]
    $pre = @($script:KitPython | Select-Object -Skip 1)
    $prev = [Console]::OutputEncoding
    # The resolver's stderr is read here, never raised: under Windows PowerShell a native stderr
    # line is an error record, and a caller's 'Stop' preference would turn a notice into a throw.
    $ErrorActionPreference = 'Continue'
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    try {
        $all = @(& $exe @pre '-B' $cli @Arguments 2>&1)
        $code = $LASTEXITCODE
    }
    finally {
        [Console]::OutputEncoding = $prev
    }
    $said = @($all | Where-Object { $_ -is [System.Management.Automation.ErrorRecord] } | ForEach-Object { "$_" })
    $out = @($all | Where-Object { $_ -isnot [System.Management.Automation.ErrorRecord] } | ForEach-Object { "$_" })
    if (-not $Quiet) { foreach ($line in $said) { [Console]::Error.WriteLine($line) } }
    if ($code -ne 0) {
        if ($Optional) { return $null }
        $why = ($said | Where-Object { $_ -match '\S' } | Select-Object -Last 1) -replace '^ERROR:\s*', ''
        throw "$why"
    }
    return $out
}

function Set-KitEnvChanges {
    param($Changes)
    if ($null -eq $Changes) { return }
    foreach ($p in $Changes.set.PSObject.Properties) { Set-Item -Path "env:$($p.Name)" -Value ([string]$p.Value) }
    foreach ($name in @($Changes.unset)) { if ($name) { Remove-Item -Path "env:$name" -ErrorAction SilentlyContinue } }
}

function Get-KitContext {
    $key = if ($env:STACK_KIT_PROJECT_ROOT) { $env:STACK_KIT_PROJECT_ROOT } else { "cwd:$((Get-Location).Path)" }
    if ($null -ne $script:KitContext -and $script:KitContextKey -eq $key) { return $script:KitContext }
    $doc = (Invoke-KitResolver -Arguments @('--shell', 'pwsh', 'context')) -join "`n" | ConvertFrom-Json
    Set-KitEnvChanges $doc.env
    $map = @{}
    foreach ($p in $doc.context.PSObject.Properties) { $map[$p.Name] = [string]$p.Value }
    $script:KitContext = $map
    $script:KitContextKey = if ($env:STACK_KIT_PROJECT_ROOT) { $env:STACK_KIT_PROJECT_ROOT } else { "cwd:$((Get-Location).Path)" }
    return $map
}

function Get-KitContextValue {
    # One context entry, or $null when absent or empty.
    param([Parameter(Mandatory = $true)][string]$Key)
    $v = (Get-KitContext)[$Key]
    if ($v) { return $v }
    return $null
}

function Get-KitContextLines {
    param([Parameter(Mandatory = $true)][string]$Key)
    $v = Get-KitContextValue $Key
    if (-not $v) { return @() }
    return @($v -split "`n" | Where-Object { $_ })
}

function Write-KitDeprecation {
    # One line, once per former name and process tree (ADR-001 decision 1).
    param([string]$Old, [string]$New)
    $doc = (Invoke-KitResolver -Arguments @('--shell', 'pwsh', 'notice', $Old, $New)) -join "`n" | ConvertFrom-Json
    Set-KitEnvChanges $doc.env
}

function Get-ProjectManifestPath {
    Get-KitContextValue 'manifest'
}

function Get-ProjectRootFromManifest {
    Get-KitContextValue 'root'
}

function Get-ManifestField {
    # A scalar manifest field: the manifest's value, else -Default when given, else the declared
    # convention default, else "".
    param([string]$Field, [string]$Default)
    $v = Get-KitContextValue "field:$Field"
    if ($null -ne $v) { return $v }
    if ($PSBoundParameters.ContainsKey('Default')) { return $Default }
    $d = Get-KitContextValue "default:$Field"
    if ($null -ne $d) { return $d }
    return ""
}

function Get-ManifestList {
    # An array-valued manifest field, one item per element (empty when absent).
    param([Parameter(Mandatory = $true)][string]$Field)
    Get-KitContextLines "list:$Field"
}

function Get-OpsPackageRoot {
    Get-KitContextValue 'packageRoot'
}

function Get-ManifestModulePath {
    param([Parameter(Mandatory = $true)][string]$ModuleId)
    if (-not (Get-ProjectRootFromManifest)) { throw "$((Get-KitIdentity).manifestFilename) not found" }
    $p = Get-KitContextValue "module:$($ModuleId):path"
    if (-not $p) { throw "module '$ModuleId' declares no path" }
    return $p
}

function Get-ModuleSecretsFolder {
    param([Parameter(Mandatory = $true)][string]$ModuleId)
    $f = Get-KitContextValue "module:$($ModuleId):secretsFolder"
    if ($f) { return $f }
    return $ModuleId
}

function Get-ModuleIdByDriverType {
    param([Parameter(Mandatory = $true)][string]$DriverType)
    Get-KitContextLines "type:$DriverType" | Select-Object -First 1
}

function Get-SecretsConfigRel {
    Get-KitContextValue 'secretsRel'
}

function Get-ModuleEnvPathLabels {
    param(
        [Parameter(Mandatory = $true)][string]$ModuleId,
        [Parameter(Mandatory = $true)][string[]]$FileNames
    )
    $base = "$(Get-SecretsConfigRel)/$(Get-ModuleSecretsFolder $ModuleId)"
    foreach ($name in $FileNames) { "$base/$name" }
}

function Get-ListedSecretsModuleFolders {
    Get-KitContextLines 'secretsFolders'
}

function Get-StackComposeDirFromManifest {
    if (-not (Get-ProjectRootFromManifest)) { throw "$((Get-KitIdentity).manifestFilename) not found" }
    Get-KitContextValue 'path:stackComposeDir'
}

function Get-InfraComposeDirFromManifest {
    if (-not (Get-ProjectRootFromManifest)) { throw "$((Get-KitIdentity).manifestFilename) not found" }
    Get-KitContextValue 'path:infraComposeDir'
}

function Get-ManifestInfraServices {
    @(Invoke-KitResolver -Arguments @('infra-services') | Where-Object { $_ })
}

function Get-InfraComposeIncludeFiles {
    @(Invoke-KitResolver -Arguments @('infra-compose-files') | Where-Object { $_ })
}

function Add-InfraComposeFileArgs {
    param([System.Collections.ArrayList]$Target)
    foreach ($a in (Invoke-KitResolver -Arguments @('infra-compose-args'))) {
        if ($a) { [void]$Target.Add($a) }
    }
}

function Get-InfraTunnelForwards {
    foreach ($line in (Invoke-KitResolver -Arguments @('infra-tunnel-forwards'))) {
        if (-not $line) { continue }
        $f = $line -split "`t"
        [pscustomobject]@{ Local = $f[0]; Remote = $f[1]; Service = $f[2]; Env = $f[3] }
    }
}

function Get-InfraSyncRelativePaths {
    @(Invoke-KitResolver -Arguments @('infra-sync-paths') | Where-Object { $_ })
}

# Resolved at load: former variables are carried to their current names before anything reads them.
$null = Get-KitContext
