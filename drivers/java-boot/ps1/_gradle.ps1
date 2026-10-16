# java-boot - the module's Gradle wrapper and task names, read from this driver's own fields
# (modules.<id>.hybrid.gradleWrapper, .gradleProject); one home for the launch step and the
# lifecycle steps. Needs lib/project.ps1 and lib/drivers.ps1 in scope.

function Resolve-GradleWrapper {
    param([string]$ModuleId, [string]$ModPath, [string]$Root)
    $wrapperRel = Get-ModuleField $ModuleId 'hybrid.gradleWrapper'
    if (-not $wrapperRel) {
        # The wrapper this platform runs: gradlew.bat on Windows, gradlew elsewhere.
        $onWindows = [System.Environment]::OSVersion.Platform -eq 'Win32NT'
        $name = if ($onWindows) { "gradlew.bat" } else { "gradlew" }
        $modRelPath = Get-ManifestField "modules.$ModuleId.path"
        if (Test-Path (Join-Path $ModPath $name)) { $wrapperRel = "$modRelPath/$name" }
    }
    if (-not $wrapperRel) {
        throw "No Gradle wrapper found; set modules.$ModuleId.hybrid.gradleWrapper in $((Get-KitIdentity).manifestFilename)"
    }
    $wrapper = Join-Path $Root ($wrapperRel -replace '/', [System.IO.Path]::DirectorySeparatorChar)
    if (-not (Test-Path $wrapper)) { throw "Gradle wrapper not found: $wrapper" }
    return $wrapper
}

function Get-GradleTask {
    # A task of the module's Gradle project (`:<project>:<task>`), or of the root build.
    param([string]$ModuleId, [string]$Task)
    $gradleProject = Get-ModuleField $ModuleId 'hybrid.gradleProject'
    if ($gradleProject) { return ":${gradleProject}:$Task" }
    return $Task
}

function Invoke-GradleStep {
    # One lifecycle step through the module's wrapper, from the module directory; its exit code.
    param([string]$ModuleId, [string]$Task, [string[]]$Rest = @())
    $root = Get-ProjectRootFromManifest
    $modPath = Get-ModuleProjectPath $ModuleId
    $wrapper = Resolve-GradleWrapper -ModuleId $ModuleId -ModPath $modPath -Root $root
    $argv = @((Get-GradleTask -ModuleId $ModuleId -Task $Task)) + $Rest
    Write-Host "  [$ModuleId $Task] $wrapper $($argv -join ' ')" -ForegroundColor Cyan
    Push-Location $modPath
    try { & $wrapper @argv | Out-Host; return $LASTEXITCODE } finally { Pop-Location }
}
