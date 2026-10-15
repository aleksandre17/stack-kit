# Resolves boot JAR path and runs java -jar (Windows-safe: avoids Gradle includeBuild file-lock).
$PackageRoot = if ($env:STACK_KIT_KIT_ROOT) { $env:STACK_KIT_KIT_ROOT } else {
    Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
}
. (Join-Path $PackageRoot "lib\module-manifest.ps1")

function Get-StackKitHybridBootJar {
    param([string]$Root, [string]$ModuleId, [string]$ModPath)
    $explicit = Get-ModuleBootJar $ModuleId
    if ($explicit) {
        return Join-Path $Root ($explicit -replace '/', '\')
    }
    $libsDir = Join-Path $ModPath "build\libs"
    if (-not (Test-Path $libsDir)) { return $null }
    $candidates = Get-ChildItem $libsDir -Filter "*.jar" |
        Where-Object { $_.Name -notmatch 'plain' -and $_.Name -match 'SNAPSHOT' } |
        Sort-Object LastWriteTime -Descending
    if ($candidates) { return $candidates[0].FullName }
    return $null
}

function Test-StackKitPreferHybridJar {
    param([string]$ModuleId)
    if ($env:STACK_KIT_HYBRID_GRADLE -eq '1') { return $false }
    if ($env:STACK_KIT_HYBRID_JAR -eq '1') { return $true }
    $pref = Get-ModulePreferHybridJar $ModuleId
    if ($pref -eq 'true') { return $true }
    if ($pref -eq 'false') { return $false }
    return $IsWindows
}

function Invoke-StackKitHybridJarBoot {
    param([string]$Root, [string]$ModuleId, [string]$ModPath)
    $jar = Get-StackKitHybridBootJar -Root $Root -ModuleId $ModuleId -ModPath $ModPath
    if (-not $jar -or -not (Test-Path $jar)) { return }

    $profiles = Get-ModuleHybridProfiles $ModuleId
    if ($profiles) { $env:SPRING_PROFILES_ACTIVE = $profiles }

    # Modules that do NOT own Flyway (datastores.postgres.flyway != true) must not run
    # DB migrations on startup — exclude DataSource + Flyway auto-configuration entirely.
    if (-not (Test-ModuleOwnsFlyway $ModuleId)) {
        $env:SPRING_FLYWAY_ENABLED = 'false'
        $env:SPRING_AUTOCONFIGURE_EXCLUDE = (
            'org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration,' +
            'org.springframework.boot.flyway.autoconfigure.FlywayAutoConfiguration'
        )
    }

    Write-Host "[hybrid] jar boot $ModuleId -> $jar" -ForegroundColor Cyan
    Set-Location $ModPath
    & java -jar $jar
    exit $LASTEXITCODE
}
