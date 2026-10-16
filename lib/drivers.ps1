# Module drivers for PowerShell -- a SHIM over the resolver's context (ADR-001 decision 2).
#
# A module's type, the registry's commands, default roles, tasks and host-run scripts, the CLI
# aliases: all are answered by lib/resolution.py from the manifest and drivers/registry.json. This
# file only looks them up, and says what is missing in the words a caller needs.

. (Join-Path $PSScriptRoot "project.ps1")

function Get-DriverRegistryPath {
    Join-Path (Get-OpsPackageRoot) "drivers\registry.json"
}

function Get-ModuleManifestEntry {
    # The module's own declaration as an object, or $null when the manifest declares no such module.
    param([string]$ModuleId)
    $json = Get-KitContextValue "module:$($ModuleId):json"
    if (-not $json) { return $null }
    return ($json | ConvertFrom-Json)
}

function Get-ModuleField {
    # A module's own field, by its path under the module (e.g. 'hybrid.npmScript'); the first of
    # several paths that holds a value, else "". The DRIVER that reads a field names it -- the kit
    # keeps no list of any driver's fields (ADR-001 amendment 7).
    param([Parameter(Mandatory = $true)][string]$ModuleId, [Parameter(Mandatory = $true)][string[]]$Path)
    $entry = Get-ModuleManifestEntry $ModuleId
    foreach ($p in $Path) {
        $v = $entry
        foreach ($name in $p.Split('.')) {
            if ($null -eq $v) { break }
            $v = $v.$name
        }
        if ($null -ne $v -and "$v" -ne "") {
            if ($v -is [bool]) { return $v.ToString().ToLowerInvariant() }
            return "$v"
        }
    }
    return ""
}

function Get-ModuleType {
    param([string]$ModuleId)
    if (-not (Get-KitContextValue "module:$($ModuleId):json")) {
        throw "Unknown module '$ModuleId' - declare it under modules in $((Get-KitIdentity).manifestFilename)"
    }
    $t = Get-KitContextValue "module:$($ModuleId):type"
    if (-not $t) { throw "module '$ModuleId' declares no type (a driver id from drivers/registry.json)" }
    return $t
}

function Get-ModuleProjectPath {
    param([string]$ModuleId)
    Get-ManifestModulePath $ModuleId
}

function Get-DriverRoot {
    param([string]$ModuleId)
    $null = Get-ModuleType $ModuleId
    Get-KitContextValue "module:$($ModuleId):driverRoot"
}

function Assert-DriverRegistered {
    param([string]$Type)
    if (-not (Get-KitContextLines 'drivers' | Where-Object { $_ -eq $Type })) {
        throw "Unknown driver type '$Type' - add drivers/$Type/ and registry.json. Known: $((Get-KitContextLines 'drivers') -join ', ')"
    }
}

function Get-DriverCapabilities {
    param([string]$ModuleId)
    $typ = Get-ModuleType $ModuleId
    Assert-DriverRegistered $typ
    Get-KitContextLines "driver:$($typ):commands"
}

function Get-DriverCommandPath {
    param(
        [string]$ModuleId,
        [string]$Command
    )
    $typ = Get-ModuleType $ModuleId
    $caps = @(Get-DriverCapabilities $ModuleId)
    if ($Command -notin $caps) {
        throw "Driver '$typ' has no command '$Command' (available: $($caps -join ', '))"
    }
    Get-KitContextValue "driver:$($typ):command:$Command"
}

# The role a driver DECLARES it serves first, used only when a module omits its own.
function Get-DriverDefaultRole {
    param([string]$Type)
    if (-not $Type) { return "" }
    $r = Get-KitContextValue "driver:$($Type):defaultRole"
    if ($r) { return $r }
    return ""
}

# The argv a driver DECLARES for a named watch loop, or $null.
function Get-DriverTaskArgs {
    param([string]$Type, [string]$TaskName)
    if (-not $Type) { return $null }
    $argv = @(Get-KitContextLines "driver:$($Type):task:$TaskName")
    if ($argv.Count -eq 0) { return $null }
    return $argv
}

# The launch script a driver DECLARES for a host-process run, or $null when it declares none.
function Get-DriverHybridScript {
    param([string]$Type)
    if (-not $Type) { return $null }
    $path = Get-KitContextValue "driver:$($Type):hybridScript"
    if (-not $path) { return $null }
    if (-not (Test-Path $path)) { throw "drivers/registry.json: $Type declares a host-run script that is missing: $path" }
    return $path
}

function Get-CliAliasesFromManifest {
    $aliases = @{}
    foreach ($key in @((Get-KitContext).Keys | Where-Object { $_ -like 'alias:*' })) {
        $aliases[$key.Substring(6)] = (Get-KitContext)[$key]
    }
    return $aliases
}

function Resolve-CliAlias {
    param([string]$Alias)
    $target = Get-KitContextValue "alias:$Alias"
    if ($target) { return $target }
    if (Get-KitContextValue "module:$($Alias):json") { return $Alias }
    return $null
}

function Get-ProjectModules {
    Get-KitContextLines 'modules'
}
