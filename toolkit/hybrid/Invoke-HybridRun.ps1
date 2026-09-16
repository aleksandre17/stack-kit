# Local app run: host process + manifest secrets (.env.dev); optional remote infra via tunnel.
param(
    [Parameter(Mandatory = $true)]
    [string]$ModuleId
)

$ErrorActionPreference = "Stop"

$PackageRoot = if ($env:GEOSTAT_KIT_ROOT) { $env:GEOSTAT_KIT_ROOT } else {
    Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
}
. (Join-Path $PackageRoot "lib\project.ps1")
. (Join-Path $PackageRoot "lib\env.ps1")
. (Join-Path $PackageRoot "lib\drivers.ps1")
. (Join-Path $PackageRoot "lib\module-manifest.ps1")

$root = Get-ProjectRootFromManifest
if (-not $root) { throw "geostat.ops.json not found" }

$entry = Get-ModuleManifestEntry $ModuleId
if (-not $entry) { throw "Unknown module: $ModuleId" }

$modPath = Get-ModuleProjectPath $ModuleId
$secretsModule = Get-ModuleSecretsFolder $ModuleId
$envDev = Join-Path (Get-SecretsModuleDir $secretsModule) ".env.dev"

function Import-GeostatDotEnv {
    param([string]$Path, [switch]$SkipEmptyValues)
    if (-not (Test-Path $Path)) { return }
    Get-Content $Path | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') { return }
        $value = $Matches[2].Trim().Trim('"').Trim("'")
        if ($SkipEmptyValues -and [string]::IsNullOrWhiteSpace($value)) { return }
        Set-Item -Path "env:$($Matches[1])" -Value $value
    }
}

$envProd = Join-Path (Get-SecretsModuleDir $secretsModule) ".env.prod"
Import-GeostatDotEnv $envProd
Import-GeostatDotEnv $envDev -SkipEmptyValues

$driverType = Get-ModuleType $ModuleId
Write-Host "[hybrid] boot $ModuleId ($driverType) env=$envDev" -ForegroundColor Cyan

switch ($driverType) {
    "java-boot" {
        . (Join-Path $PSScriptRoot "Invoke-HybridJarBoot.ps1")
        if (Test-GeostatPreferHybridJar -ModuleId $ModuleId) {
            $jar = Get-GeostatHybridBootJar -Root $root -ModuleId $ModuleId -ModPath $modPath
            if ($jar -and (Test-Path $jar)) {
                Invoke-GeostatHybridJarBoot -Root $root -ModuleId $ModuleId -ModPath $modPath
            } else {
                Write-Host "[hybrid] JAR not found - falling back to gradle bootRun (run a build first, or set hybrid.bootJar)" -ForegroundColor Yellow
            }
        }

        $profiles = Get-ModuleHybridProfiles $ModuleId
        if ($profiles) { $env:SPRING_PROFILES_ACTIVE = $profiles }

        $wrapperRel = Get-ModuleGradleWrapper $ModuleId
        if (-not $wrapperRel) {
            $modRelPath = Get-ManifestField "modules.$ModuleId.path"
            if (Test-Path (Join-Path $modPath "gradlew.bat")) {
                $wrapperRel = "$modRelPath/gradlew.bat"
            } elseif (Test-Path (Join-Path $modPath "gradlew")) {
                $wrapperRel = "$modRelPath/gradlew"
            }
        }
        if (-not $wrapperRel) {
            throw "No Gradle wrapper found; set modules.$ModuleId.hybrid.gradleWrapper in geostat.ops.json"
        }

        $wrapper = Join-Path $root ($wrapperRel -replace '/', '\')
        if (-not (Test-Path $wrapper)) { throw "Gradle wrapper not found: $wrapper" }

        $gradleProject = Get-ModuleGradleProject $ModuleId
        $bootTask = if ($gradleProject) { ":${gradleProject}:bootRun" } else { "bootRun" }

        Set-Location $modPath
        & $wrapper $bootTask -x test
        exit $LASTEXITCODE
    }
    "node-vite" {
        $npmScript = Get-ModuleNpmScript $ModuleId
        if (-not $npmScript) { $npmScript = "dev" }

        Set-Location $modPath
        npm run $npmScript
        exit $LASTEXITCODE
    }
    "node-api" {
        # pnpm-workspace Node service: run the module's dev/start script via pnpm so
        # workspace deps (e.g. @geostat/engine) resolve. Same npm-script contract as
        # node-vite, pnpm instead of npm (the api lives in a pnpm workspace).
        $npmScript = Get-ModuleNpmScript $ModuleId
        if (-not $npmScript) { $npmScript = "dev" }

        Set-Location $modPath
        if (Get-Command pnpm -ErrorAction SilentlyContinue) {
            pnpm run $npmScript
        } else {
            Write-Host "[hybrid] pnpm not on PATH - falling back to npm run $npmScript" -ForegroundColor Yellow
            npm run $npmScript
        }
        exit $LASTEXITCODE
    }
    default {
        throw ('Hybrid run not supported for driver type ''{0}'' (module {1})' -f $driverType, $ModuleId)
    }
}
