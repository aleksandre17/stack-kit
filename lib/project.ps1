# Project manifest resolution — package boundary.
#
# The manifest's NAME is not spelled here. It is declared once in lib/identity.json
# and projected into every runtime, so a rename is one edit and never an archaeology.

$script:GeostatIdentity = $null

function Get-KitIdentity {
    if ($null -ne $script:GeostatIdentity) { return $script:GeostatIdentity }
    $decl = Join-Path $PSScriptRoot 'identity.json'
    # No guessed default: a missing declaration is a broken kit, and a fallback
    # spelling here would be exactly the second home this file exists to remove.
    if (-not (Test-Path $decl)) { throw "kit identity declaration missing: $decl" }
    $script:GeostatIdentity = Get-Content -Raw -Encoding UTF8 $decl | ConvertFrom-Json
    return $script:GeostatIdentity
}

function Get-ManifestFileNames {
    # Accepted manifest filenames, canonical first.
    $id = Get-KitIdentity
    @($id.manifestFilename) + @($id.legacyManifestFilenames | Where-Object { $_ })
}

function Get-ManifestInDirectory {
    param([string]$Directory)
    foreach ($name in Get-ManifestFileNames) {
        $candidate = Join-Path $Directory $name
        if (Test-Path $candidate) { return $candidate }
    }
    return $null
}

function Get-ProjectManifestPath {
    if ($env:GEOSTAT_PROJECT_ROOT) {
        $mf = Get-ManifestInDirectory $env:GEOSTAT_PROJECT_ROOT
        if ($mf) { return $mf }
    }
    $dir = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
    while ($dir) {
        $mf = Get-ManifestInDirectory $dir
        if ($mf) { return $mf }
        $parent = Split-Path $dir -Parent
        if ($parent -eq $dir) { break }
        $dir = $parent
    }
    return $null
}

function Get-ProjectRootFromManifest {
    if ($env:GEOSTAT_PROJECT_ROOT) { return $env:GEOSTAT_PROJECT_ROOT }
    $mf = Get-ProjectManifestPath
    if ($mf) { return Split-Path $mf -Parent }
    if ($env:GEOSTAT_LEGACY_ROOT_DISCOVERY -match '^(1|true|yes|on)$') {
        $dir = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
        while ($dir) {
            if ((Test-Path (Join-Path $dir "ops\config")) -or (Test-Path (Join-Path $dir "secrets"))) { return $dir }
            $parent = Split-Path $dir -Parent
            if ($parent -eq $dir) { break }
            $dir = $parent
        }
    }
    return $null
}

function Get-ScaffoldManifestPath {
    $name = (Get-KitIdentity).manifestFilename
    if ($env:GEOSTAT_KIT_ROOT) {
        return Join-Path $env:GEOSTAT_KIT_ROOT (Join-Path 'scaffold' $name)
    }
    Join-Path (Get-OpsPackageRoot) (Join-Path 'scaffold' $name)
}

function Get-ScaffoldManifestField {
    param([string]$Field)
    $path = Get-ScaffoldManifestPath
    if (-not (Test-Path $path)) { return "" }
    $m = Get-Content $path -Raw | ConvertFrom-Json
    $v = $m
    foreach ($p in ($Field -split '\.')) {
        if ($null -eq $v) { return "" }
        $prop = $v.PSObject.Properties[$p]
        if (-not $prop) { return "" }
        $v = $prop.Value
    }
    if ($null -eq $v) { return "" }
    return [string]$v
}

function Get-ManifestField {
    param([string]$Field, [string]$Default = $null)
    if ($null -eq $Default) { $Default = Get-ScaffoldManifestField $Field }
    $mf = Get-ProjectManifestPath
    if (-not $mf -or -not (Test-Path $mf)) { return $Default }
    $m = Get-Content $mf -Raw | ConvertFrom-Json
    $v = $m
    foreach ($p in ($Field -split '\.')) {
        if ($null -eq $v) { return $Default }
        $prop = $v.PSObject.Properties[$p]
        if (-not $prop) { return $Default }
        $v = $prop.Value
    }
    if ($null -eq $v) { return $Default }
    return [string]$v
}

function Get-OpsPackageRoot {
    if ($env:OPS_PACKAGE_ROOT) { return $env:OPS_PACKAGE_ROOT }
    $proj = Get-ProjectRootFromManifest
    $rel = Get-ManifestField "package"
    return (Resolve-Path (Join-Path $proj $rel)).Path
}

function Get-OpsToolkitPowerShellRoot {
    Join-Path (Get-OpsPackageRoot) "toolkit\powershell"
}

function Get-ManifestModulePath {
    param([Parameter(Mandatory = $true)][string]$ModuleId)
    $proj = Get-ProjectRootFromManifest
    if (-not $proj) { throw "$((Get-KitIdentity).manifestFilename) not found" }
    $rel = Get-ManifestField "modules.$ModuleId.path"
    if (-not $rel) { throw "manifest modules.$ModuleId.path missing" }
    Join-Path $proj ($rel -replace '/', '\')
}

function Get-ModuleSecretsFolder {
    param([Parameter(Mandatory = $true)][string]$ModuleId)
    $sm = Get-ManifestField "modules.$ModuleId.secretsModule"
    if (-not $sm) { $sm = $ModuleId }
    return $sm
}

function Get-ModuleIdByDriverType {
    param([Parameter(Mandatory = $true)][string]$DriverType)
    $mf = Get-ProjectManifestPath
    if (-not $mf) { return $null }
    $data = Get-Content $mf -Raw | ConvertFrom-Json
    foreach ($p in $data.modules.PSObject.Properties) {
        if ($p.Value.type -eq $DriverType) { return [string]$p.Name }
    }
    return $null
}

function Get-SecretsConfigRel {
    (Get-ManifestField "secrets") -replace '\\', '/'
}

function Get-ModuleEnvPathLabels {
    param(
        [Parameter(Mandatory = $true)][string]$ModuleId,
        [Parameter(Mandatory = $true)][string[]]$FileNames
    )
    $base = "$(Get-SecretsConfigRel)/$(Get-ModuleSecretsFolder $ModuleId)"
    foreach ($name in $FileNames) { "$base/$name" }
}

function Get-DeployEnvPathLabel {
    "$(Get-SecretsConfigRel)/deploy.env"
}

function Get-ListedSecretsModuleFolders {
    $mf = Get-ProjectManifestPath
    if (-not $mf) {
        $sc = Get-ScaffoldManifestPath
        if (-not (Test-Path $sc)) { return @() }
        $data = Get-Content $sc -Raw | ConvertFrom-Json
        $seen = @{}
        $out = [System.Collections.ArrayList]@()
        foreach ($p in $data.modules.PSObject.Properties) {
            $folder = if ($p.Value.secretsModule) { [string]$p.Value.secretsModule } else { [string]$p.Name }
            if (-not $seen[$folder]) { $seen[$folder] = $true; [void]$out.Add($folder) }
        }
        return $out.ToArray()
    }
    $data = Get-Content $mf -Raw | ConvertFrom-Json
    $seen = @{}
    $out = [System.Collections.ArrayList]@()
    foreach ($p in $data.modules.PSObject.Properties) {
        $folder = if ($p.Value.secretsModule) { [string]$p.Value.secretsModule } else { [string]$p.Name }
        if (-not $seen[$folder]) {
            $seen[$folder] = $true
            [void]$out.Add($folder)
        }
    }
    return $out.ToArray()
}

function Get-StackComposeDirFromManifest {
    $proj = Get-ProjectRootFromManifest
    if (-not $proj) { throw "$((Get-KitIdentity).manifestFilename) not found" }
    $rel = Get-ManifestField "stack.composeDir"
    Join-Path $proj ($rel -replace '/', '\')
}

function Get-InfraComposeDirFromManifest {
    $proj = Get-ProjectRootFromManifest
    if (-not $proj) { throw "$((Get-KitIdentity).manifestFilename) not found" }
    $rel = Get-ManifestField "stack.infraComposeDir" "ops/compose/infra"
    Join-Path $proj ($rel -replace '/', '\')
}

function Get-ManifestInfraServices {
    $mf = Get-ProjectManifestPath
    if (-not $mf) { return @() }
    $m = Get-Content $mf -Raw | ConvertFrom-Json
    if ($m.stack.infra -and $m.stack.infra.services) {
        $arr = $m.stack.infra.services
    }
    else {
        $arr = $m.stack.infraProfiles
    }
    if ($null -eq $arr) { return @() }
    if ($arr -is [string]) { return @($arr) }
    return @($arr | ForEach-Object { [string]$_ } | Where-Object { $_ })
}

function Get-ManifestInfraComposeFileOverride {
    $mf = Get-ProjectManifestPath
    if (-not $mf) { return @() }
    $m = Get-Content $mf -Raw | ConvertFrom-Json
    if ($m.stack.infra -and $m.stack.infra.composeFiles) {
        $arr = $m.stack.infra.composeFiles
    }
    else {
        $arr = $m.stack.infraComposeFiles
    }
    if ($null -eq $arr) { return @() }
    return @($arr | ForEach-Object { [string]$_ } | Where-Object { $_ })
}

function Get-InfraComposeIncludeFiles {
    $dir = Get-InfraComposeDirFromManifest
    $override = Get-ManifestInfraComposeFileOverride
    if ($override.Count -gt 0) {
        foreach ($rel in $override) {
            $full = Join-Path $dir ($rel -replace '/', '\')
            if (-not (Test-Path $full)) {
                throw "stack.infra.composeFiles missing: $full"
            }
        }
        return $override
    }
    $base = "docker-compose.base.yml"
    $monolith = "docker-compose.yml"
    $services = Get-ManifestInfraServices
    $list = [System.Collections.ArrayList]@()
    if (Test-Path (Join-Path $dir $base)) {
        [void]$list.Add($base)
        foreach ($svc in $services) {
            $frag = "services/$svc.yml"
            $full = Join-Path $dir $frag
            if (-not (Test-Path $full)) {
                throw "stack.infra.services: missing fragment $frag (add yaml or override stack.infra.composeFiles)"
            }
            [void]$list.Add($frag)
        }
        return @($list)
    }
    if (Test-Path (Join-Path $dir $monolith)) {
        return @($monolith)
    }
    throw "No docker-compose.base.yml or docker-compose.yml under $dir"
}

function Add-InfraComposeFileArgs {
    param([System.Collections.ArrayList]$Target)
    $files = Get-InfraComposeIncludeFiles
    foreach ($rel in $files) {
        [void]$Target.Add("-f")
        [void]$Target.Add($rel)
    }
    if ($files.Count -eq 1 -and $files[0] -eq "docker-compose.yml") {
        foreach ($svc in (Get-ManifestInfraServices)) {
            [void]$Target.Add("--profile")
            [void]$Target.Add($svc)
        }
    }
}

function Get-InfraCatalogFilePaths {
    $paths = [System.Collections.ArrayList]@()
    $kitRoot = if ($env:GEOSTAT_KIT_ROOT) { $env:GEOSTAT_KIT_ROOT } else { Get-OpsPackageRoot }
    $kitCat = Join-Path $kitRoot "compose\infra-catalog.json"
    if (Test-Path $kitCat) { [void]$paths.Add($kitCat) }
    $consumerCat = Join-Path (Get-InfraComposeDirFromManifest) "infra-catalog.json"
    if (Test-Path $consumerCat) { [void]$paths.Add($consumerCat) }
    return $paths
}

function Get-InfraMergedCatalogModules {
    $merged = @{}
    foreach ($catPath in (Get-InfraCatalogFilePaths)) {
        $data = Get-Content $catPath -Raw | ConvertFrom-Json
        foreach ($prop in $data.modules.PSObject.Properties) {
            $merged[$prop.Name] = $prop.Value
        }
    }
    return $merged
}

function Get-InfraTunnelForwards {
    $services = Get-ManifestInfraServices
    if (-not $services -or $services.Count -eq 0) {
        throw "stack.infra.services is empty - declare enabled stores in $((Get-KitIdentity).manifestFilename)"
    }
    $modules = Get-InfraMergedCatalogModules
    $seen = @{}
    $out = [System.Collections.ArrayList]@()
    foreach ($sid in $services) {
        if (-not $modules.ContainsKey($sid)) {
            throw "stack.infra.services: '$sid' missing in infra-catalog (kit compose/infra-catalog.json or consumer ops/compose/infra/infra-catalog.json)"
        }
        $mod = $modules[$sid]
        if (-not $mod.tunnel) { continue }
        foreach ($spec in @($mod.tunnel)) {
            $envKey = if ($spec.PSObject.Properties['env']) { [string]$spec.env } else { [string]$spec }
            $def = ""
            if ($spec.PSObject.Properties['default']) { $def = [string]$spec.default }
            $port = Get-SecretsEnvValue -Module "infra" -Key $envKey
            if (-not $port) { $port = $def }
            if (-not $port) {
                throw "infra tunnel: set $envKey in ops/config/infra/.env.dev (service '$sid')"
            }
            if ($seen[$port]) { continue }
            $seen[$port] = $true
            [void]$out.Add([pscustomobject]@{ Local = $port; Remote = $port; Service = $sid; Env = $envKey })
        }
    }
    if ($out.Count -eq 0) {
        throw "No tunnel ports for stack.infra.services - add tunnel[] to catalog modules"
    }
    return $out
}

function Get-InfraSyncRelativePaths {
    $paths = [System.Collections.ArrayList]@(Get-InfraComposeIncludeFiles)
    $dir = Get-InfraComposeDirFromManifest
    $prod = "docker-compose.prod.yml"
    if ((Test-Path (Join-Path $dir $prod)) -and -not ($paths -contains $prod)) {
        [void]$paths.Add($prod)
    }
    $coexist = "docker-compose.coexist.yml"
    if ((Test-Path (Join-Path $dir $coexist)) -and -not ($paths -contains $coexist)) {
        [void]$paths.Add($coexist)
    }
    $readme = "README.md"
    if ((Test-Path (Join-Path $dir $readme)) -and -not ($paths -contains $readme)) {
        [void]$paths.Add($readme)
    }
    return @($paths | Select-Object -Unique)
}

function Get-DefaultRemoteDeployPathBase {
    param([Parameter(Mandatory = $true)][string]$SecretsFolder)
    $base = Get-SecretsEnvValue -Module $SecretsFolder -Key "DEPLOY_PATH"
    if ($base) { return $base.Trim().TrimEnd('/') }
    $sb = Get-DeployServerBase
    if ($sb) {
        return "$sb/$(Get-ProjectSlug)/$SecretsFolder"
    }
    return $null
}
