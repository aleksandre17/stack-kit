# java-boot - the boot JAR: resolves it and runs java -jar (Windows-safe: avoids the Gradle
# includeBuild file-lock). Dot-sourced by this driver's launch step (ps1/hybrid.ps1), with the
# runner's lib in scope; the fields read are this driver's own (modules.<id>.hybrid.*, datastores.*).

function Get-StackKitHybridBootJar {
    param([string]$Root, [string]$ModuleId, [string]$ModPath)
    $explicit = Get-ModuleField $ModuleId 'hybrid.bootJar'
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
    $pref = Get-ModuleField $ModuleId 'hybrid.preferJar'
    if ($pref -eq 'true') { return $true }
    if ($pref -eq 'false') { return $false }
    # Windows PowerShell 5.1 has no $IsWindows; the platform is asked directly.
    return [System.Environment]::OSVersion.Platform -eq 'Win32NT'
}

function Invoke-StackKitHybridJarBoot {
    param([string]$Root, [string]$ModuleId, [string]$ModPath)
    $jar = Get-StackKitHybridBootJar -Root $Root -ModuleId $ModuleId -ModPath $ModPath
    if (-not $jar -or -not (Test-Path $jar)) { return }

    $profiles = Get-ModuleField $ModuleId 'hybrid.springProfiles'
    if ($profiles) { $env:SPRING_PROFILES_ACTIVE = $profiles }

    # Modules that do NOT own Flyway (datastores.postgres.flyway != true) must not run
    # DB migrations on startup — exclude DataSource + Flyway auto-configuration entirely.
    if ((Get-ModuleField $ModuleId 'datastores.postgres.flyway') -ne 'true') {
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
