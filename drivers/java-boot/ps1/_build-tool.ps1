# java-boot - the module's build tool, resolved once for the launch step and every lifecycle step:
# `modules.<id>.java.build` when declared (maven | gradle), else the build file in the module (pom.xml:
# Maven; build.gradle(.kts): Gradle). Its wrapper beside the build file is used, else the tool on the
# PATH; with neither, the step is refused by name. No pom.xml: Gradle, as before Maven was known. The same order the driver declares (`buildTools`),
# which validate reads. Needs lib/project.ps1 and lib/drivers.ps1 in scope.

function Resolve-JvmBuildTool {
    param([string]$ModuleId, [string]$ModPath, [string]$Root)
    $onWindows = [System.Environment]::OSVersion.Platform -eq 'Win32NT'
    $kind = Get-ModuleField $ModuleId 'java.build'
    if (-not $kind) {
        $kind = if (Test-Path (Join-Path $ModPath "pom.xml")) { "maven" } else { "gradle" }
    }
    if ($kind -eq "maven") {
        $wrapperName = if ($onWindows) { "mvnw.cmd" } else { "mvnw" }
        $fallback = "mvn"
    } else {
        $wrapperName = if ($onWindows) { "gradlew.bat" } else { "gradlew" }
        $fallback = "gradle"
        $declared = Get-ModuleField $ModuleId 'hybrid.gradleWrapper'
        if ($declared) {
            $wrapper = Join-Path $Root ($declared -replace '/', [System.IO.Path]::DirectorySeparatorChar)
            if (-not (Test-Path $wrapper)) { throw "Gradle wrapper not found: $wrapper (modules.$ModuleId.hybrid.gradleWrapper)" }
            return @{ Kind = $kind; Exe = $wrapper }
        }
    }
    $wrapper = Join-Path $ModPath $wrapperName
    if (Test-Path $wrapper) { return @{ Kind = $kind; Exe = $wrapper } }
    $onPath = Get-Command $fallback -ErrorAction SilentlyContinue
    if ($onPath) {
        Write-Host "  [$ModuleId] no $wrapperName in the module: building with $fallback from the PATH" -ForegroundColor Yellow
        return @{ Kind = $kind; Exe = $onPath.Source }
    }
    throw "modules.${ModuleId}: a $kind build, with no $wrapperName in $ModPath and no $fallback on the PATH -- commit the wrapper, or install $fallback"
}

function Get-JvmStepArgs {
    # The arguments of one lifecycle step for the module's tool: build (no tests), test, run.
    param([string]$ModuleId, [string]$Kind, [string]$Step)
    if ($Kind -eq "maven") {
        switch ($Step) {
            "build" { return @("-q", "package", "-DskipTests") }
            "test" { return @("-q", "test") }
            "run" { return @("-q", "spring-boot:run") }
        }
    }
    $gradleProject = Get-ModuleField $ModuleId 'hybrid.gradleProject'
    $task = switch ($Step) { "build" { "build" } "test" { "test" } "run" { "bootRun" } }
    $named = if ($gradleProject) { ":${gradleProject}:$task" } else { $task }
    switch ($Step) {
        "build" { return @($named, "-x", "test") }
        "run" { return @($named, "-x", "test") }
        default { return @($named) }
    }
}

function Invoke-JvmStep {
    # One lifecycle step through the module's tool, from the module directory; its exit code.
    param([string]$ModuleId, [string]$Step, [string[]]$Rest = @())
    $root = Get-ProjectRootFromManifest
    $modPath = Get-ModuleProjectPath $ModuleId
    try { $tool = Resolve-JvmBuildTool -ModuleId $ModuleId -ModPath $modPath -Root $root }
    catch { Write-Host "  [$ModuleId $Step] $($_.Exception.Message)" -ForegroundColor Red; return 1 }
    $argv = @(Get-JvmStepArgs -ModuleId $ModuleId -Kind $tool.Kind -Step $Step) + $Rest
    Write-Host "  [$ModuleId $Step] $($tool.Exe) $($argv -join ' ')" -ForegroundColor Cyan
    Push-Location $modPath
    try { & $tool.Exe @argv | Out-Host; return $LASTEXITCODE } finally { Pop-Location }
}
