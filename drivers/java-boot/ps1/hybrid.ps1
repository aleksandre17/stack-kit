# java-boot - launch step, dot-sourced by toolkit/hybrid/Invoke-HybridRun.ps1 after the module's
# run environment was imported. A built boot JAR when preferred and present, else the build tool's run
# (Gradle bootRun, Maven spring-boot:run).
# In scope from the caller: $ModuleId, $modPath, $root, $PackageRoot.

. (Join-Path $PSScriptRoot "_jar-boot.ps1")
if (Test-StackKitPreferHybridJar -ModuleId $ModuleId) {
    $jar = Get-StackKitHybridBootJar -Root $root -ModuleId $ModuleId -ModPath $modPath
    if ($jar -and (Test-Path $jar)) {
        Invoke-StackKitHybridJarBoot -Root $root -ModuleId $ModuleId -ModPath $modPath
    } else {
        Write-Host "[hybrid] JAR not found - falling back to the build tool's run (run a build first, or set hybrid.bootJar)" -ForegroundColor Yellow
    }
}

$profiles = Get-ModuleField $ModuleId 'hybrid.springProfiles'
if ($profiles) { $env:SPRING_PROFILES_ACTIVE = $profiles }

. (Join-Path $PSScriptRoot "_build-tool.ps1")
$tool = Resolve-JvmBuildTool -ModuleId $ModuleId -ModPath $modPath -Root $root
$argv = Get-JvmStepArgs -ModuleId $ModuleId -Kind $tool.Kind -Step "run"
Push-Location $modPath
try { & $tool.Exe @argv } finally { Pop-Location }
exit $LASTEXITCODE
