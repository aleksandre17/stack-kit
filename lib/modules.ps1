# Modules for PowerShell -- roles, types, layout routing, compose names: a SHIM over the resolver
# (ADR-001 decision 2). No driver and no module id is named here.

. (Join-Path $PSScriptRoot "project.ps1")
. (Join-Path $PSScriptRoot "drivers.ps1")

function Invoke-StackKitModulesApi {
    param([string[]]$ApiArgs)
    if (-not $script:KitPython) {
        $script:KitPython = Get-StackKitPythonArgs
        if (-not $script:KitPython) { throw "Python not found (tried py -3, python3, python)" }
    }
    $script = Join-Path (Get-OpsPackageRoot) "lib\modules_cli.py"
    Invoke-StackKitPythonExe $script:KitPython $script @ApiArgs
}

function Get-ModuleRole {
    param([Parameter(Mandatory = $true)][string]$ModuleId)
    Get-KitContextValue "module:$($ModuleId):role"
}

function Get-ModuleIdsByRole {
    param([Parameter(Mandatory = $true)][string]$Role)
    Get-KitContextLines "role:$Role"
}

function Get-ModuleIdByRole {
    param(
        [Parameter(Mandatory = $true)][string]$Role,
        [int]$Index = 0
    )
    $ids = @(Get-ModuleIdsByRole $Role)
    if ($Index -lt $ids.Count) { return $ids[$Index] }
    return $null
}

function Get-ModuleIdsByDriverType {
    param([Parameter(Mandatory = $true)][string]$DriverType)
    Get-KitContextLines "type:$DriverType"
}

function Get-LayoutSimulatorScript {
    # The layout simulator the module's driver DECLARES, or $null.
    param([Parameter(Mandatory = $true)][string]$ModuleId)
    Get-KitContextValue "driver:$(Get-ModuleType $ModuleId):layoutSimulator"
}

function Invoke-ModuleLayoutSimulator {
    param(
        [Parameter(Mandatory = $true)][string]$ModuleId,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$LayoutArgs
    )
    $sim = Get-LayoutSimulatorScript $ModuleId
    if (-not $sim) {
        throw "No layout simulator for module '$ModuleId' (type $(Get-ModuleType $ModuleId))"
    }
    $path = Join-Path (Join-Path (Get-OpsPackageRoot) "toolkit\layout") $sim
    & $path -ModuleId $ModuleId @LayoutArgs
}

function Get-InferredCliAliases {
    Get-CliAliasesFromManifest
}

function Get-ModuleComposeServiceName {
    param([Parameter(Mandatory = $true)][string]$ModuleId)
    $out = Invoke-StackKitModulesApi @("compose-service", $ModuleId)
    if ($out) { return $out.Trim() }
    return $null
}

function Get-ComposeAppServiceName {
    # The UI service's compose name, as the one naming rule (lib/compose_identity.py) gives it.
    $names = (Invoke-StackKitModulesApi @("compose-names")) -join "`n" | ConvertFrom-Json
    return [string]$names.app
}

function Write-StackEndpointHints {
    $lines = Invoke-StackKitModulesApi @("stack-endpoints")
    if (-not $lines) { return }
    foreach ($line in ($lines -split "`n")) {
        $t = $line.Trim()
        if ($t) { Write-Host "  $t" -ForegroundColor Gray }
    }
}
