# Module driver resolution — manifest type + drivers/registry.json (see lib/driver_api.py)

. (Join-Path $PSScriptRoot "stack-kit-python.ps1")

function Get-DriverApiScript {
    Join-Path (Get-OpsPackageRoot) "lib\driver_api.py"
}

function Invoke-DriverApi {
    param([string[]]$ApiArgs)
    $pyArgs = Get-StackKitPythonArgs
    if (-not $pyArgs) { throw "Python not found (tried py -3, python3, python)" }
    Invoke-StackKitPythonExe $pyArgs (Get-DriverApiScript) @ApiArgs
    if ($LASTEXITCODE -ne 0) { throw "driver_api failed" }
}

function Get-DriverRegistryPath {
    Join-Path (Get-OpsPackageRoot) "drivers\registry.json"
}

function Get-ModuleManifestEntry {
    param([string]$ModuleId)
    $mf = Get-ProjectManifestPath
    if (-not $mf -or -not (Test-Path $mf)) { return $null }
    $data = Get-Content $mf -Raw | ConvertFrom-Json
    if (-not $data.modules.PSObject.Properties[$ModuleId]) { return $null }
    return $data.modules.$ModuleId
}

function Get-ModuleType {
    param([string]$ModuleId)
    $m = Get-ModuleManifestEntry $ModuleId
    if (-not $m) {
        throw "Unknown module '$ModuleId' - add modules.$ModuleId in $((Get-KitIdentity).manifestFilename)"
    }
    if (-not $m.type) {
        throw "modules.$ModuleId.type is required (driver id from drivers/registry.json)"
    }
    return [string]$m.type
}

function Get-ModuleProjectPath {
    param([string]$ModuleId)
    $root = Get-ProjectRootFromManifest
    $m = Get-ModuleManifestEntry $ModuleId
    $rel = if ($m.path) { $m.path } else { $ModuleId }
    Join-Path $root $rel
}

function Get-DriverRoot {
    param([string]$ModuleId)
    Join-Path (Get-OpsPackageRoot) "drivers\$(Get-ModuleType $ModuleId)"
}

function Get-DriverRegistryEntry {
    param([string]$Type)
    $reg = Get-Content (Get-DriverRegistryPath) -Raw | ConvertFrom-Json
    if (-not $reg.PSObject.Properties[$Type]) {
        $known = ($reg.PSObject.Properties.Name) -join ", "
        throw "Unknown driver type '$Type' - add drivers/$Type/ and registry.json. Known: $known"
    }
    return $reg.$Type
}

function Get-DriverCapabilities {
    param([string]$ModuleId)
    $typ = Get-ModuleType $ModuleId
    $entry = Get-DriverRegistryEntry $typ
    @($entry.commands.PSObject.Properties.Name)
}

function Get-DriverCommandPath {
    param(
        [string]$ModuleId,
        [string]$Command
    )
    $caps = Get-DriverCapabilities $ModuleId
    if ($Command -notin $caps) {
        throw "Driver '$(Get-ModuleType $ModuleId)' has no command '$Command' (available: $($caps -join ', '))"
    }
    $entry = Get-DriverRegistryEntry (Get-ModuleType $ModuleId)
    Join-Path (Get-DriverRoot $ModuleId) $entry.commands.$Command
}

# The role a driver DECLARES it serves first (drivers/registry.json "roles"), used only
# when a module omits an explicit role. No driver name is known to this file.
function Get-DriverDefaultRole {
    param([string]$Type)
    if (-not $Type) { return "" }
    $reg = Get-Content (Get-DriverRegistryPath) -Raw | ConvertFrom-Json
    if (-not $reg.PSObject.Properties[$Type]) { return "" }
    $roles = @($reg.$Type.roles)
    if ($roles.Count -gt 0) { return [string]$roles[0] }
    return ""
}

# The argv a driver DECLARES for a named watch loop (registry "tasks"), or $null.
function Get-DriverTaskArgs {
    param([string]$Type, [string]$TaskName)
    if (-not $Type) { return $null }
    $reg = Get-Content (Get-DriverRegistryPath) -Raw | ConvertFrom-Json
    if (-not $reg.PSObject.Properties[$Type]) { return $null }
    $tasks = $reg.$Type.tasks
    if (-not $tasks -or -not $tasks.PSObject.Properties[$TaskName]) { return $null }
    return @($tasks.$TaskName)
}

# The launch script a driver DECLARES for a host-process run (registry "hybrid.script"),
# resolved under drivers/<type>/, or $null when the driver declares none.
function Get-DriverHybridScript {
    param([string]$Type)
    if (-not $Type) { return $null }
    $reg = Get-Content (Get-DriverRegistryPath) -Raw | ConvertFrom-Json
    if (-not $reg.PSObject.Properties[$Type]) { return $null }
    $hybrid = $reg.$Type.hybrid
    if (-not $hybrid -or -not $hybrid.script) { return $null }
    $path = Join-Path (Join-Path (Get-OpsPackageRoot) "drivers\$Type") $hybrid.script
    if (-not (Test-Path $path)) { throw "drivers/registry.json: $Type.hybrid.script points to a missing file: $path" }
    return $path
}

function Get-CliAliasesFromManifest {
    $mf = Get-ProjectManifestPath
    if (-not $mf) { return @{} }
    $data = Get-Content $mf -Raw | ConvertFrom-Json
    $aliases = @{}
    if ($data.cli -and $data.cli.aliases) {
        $data.cli.aliases.PSObject.Properties | ForEach-Object {
            $aliases[$_.Name] = [string]$_.Value
        }
    }
    $used = [System.Collections.Generic.HashSet[string]]::new()
    foreach ($v in $aliases.Values) { [void]$used.Add($v) }
    foreach ($role in @("ui", "api", "worker", "gateway")) {
        $ids = @(
            $data.modules.PSObject.Properties |
                Where-Object {
                    $r = $_.Value.role
                    if (-not $r) { $r = Get-DriverDefaultRole ([string]$_.Value.type) }
                    $r -eq $role
                } |
                ForEach-Object { $_.Name }
        )
        if ($ids.Count -eq 1 -and -not $used.Contains($ids[0])) {
            if (-not $aliases.ContainsKey($role)) { $aliases[$role] = $ids[0] }
            [void]$used.Add($ids[0])
        }
    }
    return $aliases
}

function Resolve-CliAlias {
    param([string]$Alias)
    $aliases = Get-CliAliasesFromManifest
    if ($aliases.ContainsKey($Alias)) { return $aliases[$Alias] }
    $mf = Get-ProjectManifestPath
    if ($mf) {
        $data = Get-Content $mf -Raw | ConvertFrom-Json
        if ($data.modules.PSObject.Properties[$Alias]) { return $Alias }
    }
    return $null
}

function Get-ProjectModules {
    $mf = Get-ProjectManifestPath
    if (-not $mf) { return @() }
    $data = Get-Content $mf -Raw | ConvertFrom-Json
    @($data.modules.PSObject.Properties.Name)
}
