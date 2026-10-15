# N-module manifest helpers (roles, types, layout routing)

. (Join-Path $PSScriptRoot "project.ps1")
. (Join-Path $PSScriptRoot "stack-kit-python.ps1")
. (Join-Path $PSScriptRoot "drivers.ps1")

function Invoke-StackKitModulesApi {
    param([string[]]$ApiArgs)
    $pyArgs = Get-StackKitPythonArgs
    if (-not $pyArgs) { throw "Python not found (tried py -3, python3, python)" }
    $script = Join-Path (Get-OpsPackageRoot) "lib\modules_cli.py"
    Invoke-StackKitPythonExe $pyArgs $script @ApiArgs
}

function Get-ModuleRole {
    param([Parameter(Mandatory = $true)][string]$ModuleId)
    Invoke-StackKitModulesApi @("role", $ModuleId)
}

function Get-ModuleIdsByRole {
    param([Parameter(Mandatory = $true)][string]$Role)
    $out = Invoke-StackKitModulesApi @("by-role", $Role)
    if ($out) { return $out -split "`n" | Where-Object { $_ } }
    return @()
}

function Get-ModuleIdByRole {
    param(
        [Parameter(Mandatory = $true)][string]$Role,
        [int]$Index = 0
    )
    $ids = Get-ModuleIdsByRole $Role
    if ($Index -lt $ids.Count) { return $ids[$Index] }
    return $null
}

function Get-ModuleIdsByDriverType {
    param([Parameter(Mandatory = $true)][string]$DriverType)
    $mf = Get-ProjectManifestPath
    if (-not $mf) { return @() }
    $data = Get-Content $mf -Raw | ConvertFrom-Json
    @($data.modules.PSObject.Properties | Where-Object { $_.Value.type -eq $DriverType } | ForEach-Object { $_.Name })
}

function Get-LayoutSimulatorScript {
    param([Parameter(Mandatory = $true)][string]$ModuleId)
    $typ = Get-ModuleType $ModuleId
    switch ($typ) {
        "node-vite" { return "simulate-frontend-layout.ps1" }
        "java-boot" { return "simulate-backend-layout.ps1" }
        default { return $null }
    }
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
    $n = Get-ModuleComposeServiceName -ModuleId "frontend"
    if ($n) { return $n }
    $fromDeploy = Get-DeployEnvValue "COMPOSE_APP_SERVICE"
    if ($fromDeploy) { return $fromDeploy }
    "$(Get-ComposeSlug)-app"
}

function Write-StackEndpointHints {
    $lines = Invoke-StackKitModulesApi @("stack-endpoints")
    if (-not $lines) { return }
    foreach ($line in ($lines -split "`n")) {
        $t = $line.Trim()
        if ($t) { Write-Host "  $t" -ForegroundColor Gray }
    }
}
