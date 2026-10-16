# java-boot - launch step, dot-sourced by toolkit/hybrid/Invoke-HybridRun.ps1 after the module's
# run environment was imported. A built boot JAR when preferred and present, else Gradle bootRun.
# In scope from the caller: $ModuleId, $modPath, $root, $PackageRoot.

. (Join-Path $PSScriptRoot "_jar-boot.ps1")
if (Test-StackKitPreferHybridJar -ModuleId $ModuleId) {
    $jar = Get-StackKitHybridBootJar -Root $root -ModuleId $ModuleId -ModPath $modPath
    if ($jar -and (Test-Path $jar)) {
        Invoke-StackKitHybridJarBoot -Root $root -ModuleId $ModuleId -ModPath $modPath
    } else {
        Write-Host "[hybrid] JAR not found - falling back to gradle bootRun (run a build first, or set hybrid.bootJar)" -ForegroundColor Yellow
    }
}

$profiles = Get-ModuleField $ModuleId 'hybrid.springProfiles'
if ($profiles) { $env:SPRING_PROFILES_ACTIVE = $profiles }

. (Join-Path $PSScriptRoot "_gradle.ps1")
$wrapper = Resolve-GradleWrapper -ModuleId $ModuleId -ModPath $modPath -Root $root
$bootTask = Get-GradleTask -ModuleId $ModuleId -Task "bootRun"

& $wrapper $bootTask -x test
exit $LASTEXITCODE
