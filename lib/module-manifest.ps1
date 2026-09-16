# Typed module manifest accessors — single source of truth for all manifest field paths.
# Wraps Get-ManifestField so that schema renames touch exactly one file.
# Consumers: Invoke-HybridRun.ps1, Invoke-HybridJarBoot.ps1, Invoke-DevUp.ps1.
# DO NOT call Get-ManifestField "modules.X.Y.Z" directly in toolkit scripts — use these.

. (Join-Path $PSScriptRoot "project.ps1")

# ── Hybrid run ────────────────────────────────────────────────────────────────

function Get-ModuleHybridProfiles {
    param([Parameter(Mandatory = $true)][string]$ModuleId)
    Get-ManifestField "modules.$ModuleId.hybrid.springProfiles"
}

function Get-ModuleGradleWrapper {
    param([Parameter(Mandatory = $true)][string]$ModuleId)
    Get-ManifestField "modules.$ModuleId.hybrid.gradleWrapper"
}

function Get-ModuleGradleProject {
    param([Parameter(Mandatory = $true)][string]$ModuleId)
    Get-ManifestField "modules.$ModuleId.hybrid.gradleProject"
}

function Get-ModuleBootJar {
    param([Parameter(Mandatory = $true)][string]$ModuleId)
    Get-ManifestField "modules.$ModuleId.hybrid.bootJar"
}

function Get-ModulePreferHybridJar {
    param([Parameter(Mandatory = $true)][string]$ModuleId)
    Get-ManifestField "modules.$ModuleId.hybrid.preferJar"
}

# ── Frontend ──────────────────────────────────────────────────────────────────

function Get-ModuleNpmScript {
    # Checks debug.npmScript first (VS Code launch), then hybrid.npmScript fallback.
    param([Parameter(Mandatory = $true)][string]$ModuleId)
    $s = Get-ManifestField "modules.$ModuleId.debug.npmScript"
    if (-not $s) { $s = Get-ManifestField "modules.$ModuleId.hybrid.npmScript" }
    return $s
}

# ── Schema / Flyway ───────────────────────────────────────────────────────────

function Test-ModuleOwnsFlyway {
    # Returns $true only when the module declares datastores.postgres.flyway=true.
    # Any module where this returns $false MUST NOT run Flyway — exclude DataSource
    # and Flyway auto-configuration on hybrid jar boot to avoid connection failures.
    param([Parameter(Mandatory = $true)][string]$ModuleId)
    $v = Get-ManifestField "modules.$ModuleId.datastores.postgres.flyway"
    return ($v -eq 'true')
}

# ── Spring ────────────────────────────────────────────────────────────────────

function Get-ModulePortEnv {
    param([Parameter(Mandatory = $true)][string]$ModuleId)
    Get-ManifestField "modules.$ModuleId.spring.portEnv"
}

function Get-ModuleSpringAppName {
    param([Parameter(Mandatory = $true)][string]$ModuleId)
    Get-ManifestField "modules.$ModuleId.spring.applicationName"
}

function Get-ModuleDefaultProfile {
    param([Parameter(Mandatory = $true)][string]$ModuleId)
    Get-ManifestField "modules.$ModuleId.spring.defaultProfile"
}

# ── Spring profile groups ─────────────────────────────────────────────────────

function Get-ModuleProfileGroup {
    # Returns the expanded profile list for a named group (e.g. "hybrid" -> ["db","hybrid-env"]).
    param(
        [Parameter(Mandatory = $true)][string]$ModuleId,
        [Parameter(Mandatory = $true)][string]$GroupName
    )
    $mf = Get-ProjectManifestPath
    if (-not $mf) { return @() }
    $data = Get-Content $mf -Raw | ConvertFrom-Json
    $groups = $data.modules.$ModuleId.spring.profileGroups
    if ($null -eq $groups) { return @() }
    $list = $groups.$GroupName
    if ($null -eq $list) { return @() }
    return @($list | ForEach-Object { [string]$_ })
}