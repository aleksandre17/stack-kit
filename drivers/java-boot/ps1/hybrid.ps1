# java-boot - launch step, dot-sourced by toolkit/hybrid/Invoke-HybridRun.ps1 after the module's
# run environment was imported. A built boot JAR when preferred and present, else Gradle bootRun.
# In scope from the caller: $ModuleId, $modPath, $root, $PackageRoot.

. (Join-Path $PackageRoot "toolkit\hybrid\Invoke-HybridJarBoot.ps1")
if (Test-StackKitPreferHybridJar -ModuleId $ModuleId) {
    $jar = Get-StackKitHybridBootJar -Root $root -ModuleId $ModuleId -ModPath $modPath
    if ($jar -and (Test-Path $jar)) {
        Invoke-StackKitHybridJarBoot -Root $root -ModuleId $ModuleId -ModPath $modPath
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
    throw "No Gradle wrapper found; set modules.$ModuleId.hybrid.gradleWrapper in $((Get-KitIdentity).manifestFilename)"
}

$wrapper = Join-Path $root ($wrapperRel -replace '/', '\')
if (-not (Test-Path $wrapper)) { throw "Gradle wrapper not found: $wrapper" }

$gradleProject = Get-ModuleGradleProject $ModuleId
$bootTask = if ($gradleProject) { ":${gradleProject}:bootRun" } else { "bootRun" }

& $wrapper $bootTask -x test
exit $LASTEXITCODE
