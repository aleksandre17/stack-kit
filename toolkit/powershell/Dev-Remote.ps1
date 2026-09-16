# Remote dev workspace — stack-agnostic (Vite, Angular CLI, Nx SPA, …)
# Dot-source after Deploy-Path.ps1. Module overrides via ops.config.ps1:
#   $OpsDevSyncExcludes, $OpsDevSyncExtraPaths, $OpsDevComposeDevFiles

function Convert-ToRsyncSourcePath {
    param([Parameter(Mandatory = $true)][string]$Path)
    $full = [System.IO.Path]::GetFullPath($Path)
    if ($full -match '^([A-Za-z]):\\(.*)$') {
        return "/$($Matches[1].ToLower())/$($Matches[2] -replace '\\', '/')"
    }
    return ($full -replace '\\', '/')
}

function Get-DevRsyncExecutable {
    $candidates = @(
        "${env:ProgramFiles}\Git\usr\bin\rsync.exe",
        "${env:ProgramFiles}\Git\bin\rsync.exe",
        "rsync"
    )
    foreach ($c in $candidates) {
        if ($c -eq "rsync") {
            $cmd = Get-Command rsync -ErrorAction SilentlyContinue
            if ($cmd) { return $cmd.Source }
        } elseif (Test-Path $c) { return $c }
    }
    if (Get-Command wsl -ErrorAction SilentlyContinue) {
        $wslRsync = wsl -e bash -lc "command -v rsync" 2>$null
        if ($LASTEXITCODE -eq 0 -and $wslRsync) { return "wsl" }
    }
    return $null
}

function Get-DevRsyncExcludeArgs {
    $excludes = @(
        "node_modules/", "dist/", "build/", ".git/", ".idea/", ".vscode/",
        "logs/", "coverage/", ".angular/", "tmp/", ".turbo/", ".next/",
        "deploy-staging/", ".cache/", "*.log"
    )
    if ($script:OpsDevSyncExcludes) {
        $excludes += @($script:OpsDevSyncExcludes)
    }
    if (Test-DevComposeRootDeclared) {
        # Rendered compose files are published separately; keep rsync --delete off them.
        $excludes += @(Get-DevComposeFileNames -Environment "dev") + @(Get-DevComposeFileNames -Environment "prod")
    }
    foreach ($e in $excludes) {
        $x = $e.Trim().TrimEnd('/')
        if ($x) { "--exclude=$x" }
    }
}

function Get-DevComposeFileNames {
    param([ValidateSet("dev", "prod")][string]$Environment = "dev")
    if ($script:OpsDevComposeDevFiles -and $Environment -eq "dev") {
        return @("docker-compose.yml") + @($script:OpsDevComposeDevFiles)
    }
    if ($Environment -eq "dev") { return @("docker-compose.yml", "docker-compose.override.yml") }
    return @("docker-compose.yml", "docker-compose.prod.yml")
}

function Get-DevComposeFileArgs {
    param([ValidateSet("dev", "prod")][string]$Environment = "dev")
    return ((Get-DevComposeFileNames -Environment $Environment) | ForEach-Object { "-f $_" }) -join " "
}

function Get-RelativePathPosix {
    param([Parameter(Mandatory = $true)][string]$From, [Parameter(Mandatory = $true)][string]$To)
    $sep = [System.IO.Path]::DirectorySeparatorChar
    $f = [System.IO.Path]::GetFullPath($From).TrimEnd([char]92, [char]47) + $sep
    $t = [System.IO.Path]::GetFullPath($To).TrimEnd([char]92, [char]47) + $sep
    $rel = [Uri]::UnescapeDataString(([Uri]$f).MakeRelativeUri([Uri]$t).ToString()).TrimEnd('/')
    if (-not $rel) { return "." }
    return $rel
}

# Rewrite host paths that point from the compose authority to the module source so
# the file resolves inside the synced workspace (module root == compose dir on server).
function ConvertTo-WorkspaceComposeText {
    param([Parameter(Mandatory = $true)][string]$Text, [Parameter(Mandatory = $true)][string]$RelativeModulePath)
    if ($RelativeModulePath -eq ".") { return $Text }
    $pattern = '(?<![\w.\-/])' + [regex]::Escape($RelativeModulePath) + '(?=[/:"''\s]|$)'
    return [regex]::Replace($Text, $pattern, ".", [System.Text.RegularExpressions.RegexOptions]::Multiline)
}

function Test-DevComposeRootDeclared {
    if (-not $script:OpsComposeRoot -or -not $script:BUILD_CONTEXT) { return $false }
    $a = [System.IO.Path]::GetFullPath($script:OpsComposeRoot).TrimEnd([char]92, [char]47)
    $b = [System.IO.Path]::GetFullPath($script:BUILD_CONTEXT).TrimEnd([char]92, [char]47)
    return ($a -ne $b)
}

function Publish-DevComposeFiles {
    param([ValidateSet("dev", "prod")][string]$Environment = "dev")
    if (-not (Test-DevComposeRootDeclared)) { return 0 }
    $composeRoot = $script:OpsComposeRoot
    $rel = Get-RelativePathPosix -From $composeRoot -To $script:BUILD_CONTEXT
    $stage = Join-Path ([System.IO.Path]::GetTempPath()) ("geostat-compose-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $stage | Out-Null
    try {
        foreach ($name in (Get-DevComposeFileNames -Environment $Environment)) {
            $src = Join-Path $composeRoot $name
            if (-not (Test-Path $src)) {
                Log "compose file missing: $src" "ERROR"
                return 1
            }
            $text = ConvertTo-WorkspaceComposeText -Text ([System.IO.File]::ReadAllText($src)) -RelativeModulePath $rel
            $out = Join-Path $stage $name
            [System.IO.File]::WriteAllText($out, ($text -replace "`r`n", "`n"), (New-Object System.Text.UTF8Encoding($false)))
            $rc = Invoke-SCP -Source $out -Dest "$($script:DEPLOY_PATH)/$name"
            if ($rc -ne 0) { Log "compose publish FAILED: $name" "ERROR"; return 1 }
        }
        Log "compose files rendered from $composeRoot" "OK"
        return 0
    } finally {
        Remove-Item -Recurse -Force $stage -ErrorAction SilentlyContinue
    }
}

function Invoke-DevRsyncToRemote {
    param([switch]$DryRun)
    if (-not $script:DEPLOY_PATH -or -not $script:SERVER) {
        throw "DEPLOY_PATH and DEPLOY_SERVER required"
    }
    $rsync = Get-DevRsyncExecutable
    if (-not $rsync) {
        Log "rsync not found (Git for Windows usr/bin/rsync or WSL)" "ERROR"
        Log "Install Git for Windows or: wsl --install" "INFO"
        return 1
    }

    $localRoot = $script:BUILD_CONTEXT
    if (-not (Test-Path $localRoot)) {
        Log "BUILD_CONTEXT missing: $localRoot" "ERROR"
        return 1
    }

    Invoke-SSH "mkdir -p '$($script:DEPLOY_PATH)'" | Out-Null
    if ($LASTEXITCODE -ne 0) { return 1 }

    $src = Convert-ToRsyncSourcePath $localRoot
    $dest = "$($script:SERVER):$($script:DEPLOY_PATH)/"
    $excludeArgs = Get-DevRsyncExcludeArgs

    $extraPaths = @()
    if ($script:OpsDevSyncExtraPaths) {
        foreach ($rel in $script:OpsDevSyncExtraPaths) {
            $p = Join-Path $MONOREPO $rel
            if (Test-Path $p) { $extraPaths += $p }
        }
    }

    Log "rsync -> $($script:DEPLOY_PATH)" "INFO"
    if ($DryRun) { Log "(dry-run)" "INFO" }

    $dryFlag = if ($DryRun) { @("--dry-run") } else { @() }
    # Carry declared DEPLOY_SSH_* settings into rsync's transport (Invoke-SSH/SCP already honour them).
    $sshExtra = @()
    if (Get-Command Get-GeostatSshExtraArgs -ErrorAction SilentlyContinue) { $sshExtra = @(Get-GeostatSshExtraArgs) }
    if ($sshExtra.Count -gt 0) {
        $rsh = "ssh " + (($sshExtra | ForEach-Object { $_.Replace([string][char]92, "/") }) -join " ")
        $dryFlag = @("-e", $rsh) + $dryFlag
    }

    if ($rsync -eq "wsl") {
        $wslSrc = $src
        if ($src -match '^/([a-z])/(.+)$') {
            $wslSrc = "/mnt/$($Matches[1])/$($Matches[2])"
        }
        $wslArgs = @("rsync", "-avz", "--delete") + $dryFlag + $excludeArgs + @("${wslSrc}/", $dest)
        & wsl @wslArgs
        $code = $LASTEXITCODE
    } else {
        $argList = @("-avz", "--delete") + $dryFlag + $excludeArgs + @("${src}/", $dest)
        # rsync's (verbose) stdout must NOT leak into this function's output stream, or the
        # caller's `$rc = Invoke-DevRsyncToRemote` captures [file-list… , $code] as an ARRAY
        # and `$rc -ne 0` is truthy → false failure. Route it to the host; keep $LASTEXITCODE.
        & $rsync @argList 2>&1 | Out-Host
        $code = $LASTEXITCODE
    }

    foreach ($extra in $extraPaths) {
        if ($rsync -eq "wsl") { continue }
        $esrc = Convert-ToRsyncSourcePath $extra
        $edest = "$($script:SERVER):$($script:DEPLOY_PATH)/"
        & $rsync @("-avz") + $dryFlag + @("${esrc}/", $edest)
        if ($LASTEXITCODE -ne 0) { $code = $LASTEXITCODE }
    }

    if ($code -eq 0) { Log "rsync OK" "OK" } else { Log "rsync FAILED (exit $code)" "ERROR" }
    return $code
}

function Invoke-DevRemoteComposeUp {
    param(
        [ValidateSet("dev", "prod")][string]$Environment = "dev",
        [switch]$Build,
        [switch]$Recreate
    )
    $remoteEnvName = Publish-RemoteEnvFiles -Environment $Environment
    if ((Publish-DevComposeFiles -Environment $Environment) -ne 0) { return 1 }
    $composeArgs = Get-DevComposeFileArgs -Environment $Environment
    $buildFlag = if ($Build) { "--build" } else { "" }
    $recreateFlag = if ($Recreate) { "--force-recreate" } else { "" }

    $remoteScript = @"
set -euo pipefail
cd '$($script:DEPLOY_PATH)'
set -a
source ./$remoteEnvName
set +a
export DEPLOY_HOST_PORT=${script:HOST_PORT}
if docker compose version >/dev/null 2>&1; then
  docker compose --env-file ./$remoteEnvName $composeArgs up -d $buildFlag $recreateFlag
else
  docker-compose --env-file ./$remoteEnvName $composeArgs up -d $buildFlag $recreateFlag
fi
docker ps --filter name=$($script:APP_NAME)
"@
    return (Invoke-SSH $remoteScript)
}

function Invoke-DevRemoteComposeRestart {
    param([ValidateSet("dev", "prod")][string]$Environment = "dev")
    $remoteEnvName = ".env.$Environment"
    $composeArgs = Get-DevComposeFileArgs -Environment $Environment
    $remoteScript = @"
set -euo pipefail
cd '$($script:DEPLOY_PATH)'
if docker compose version >/dev/null 2>&1; then
  docker compose --env-file ./$remoteEnvName $composeArgs restart
else
  docker-compose --env-file ./$remoteEnvName $composeArgs restart
fi
"@
    return (Invoke-SSH $remoteScript)
}

function Get-DevWatchRoots {
    $root = $script:BUILD_CONTEXT
    $candidates = @(
        "src", "public", "projects", "app", "libs", "e2e",
        "index.html", "angular.json", "project.json", "nx.json",
        "package.json", "tsconfig.json", "tsconfig.app.json", "tsconfig.spec.json",
        "vite.config.ts", "vite.config.js", "vite.config.mts",
        "tailwind.config.js", "postcss.config.js", "components.json",
        "docker-compose.yml", "docker-compose.override.yml", "docker-compose.prod.yml",
        "ops.config.ps1"
    )
    if ($script:OpsDevWatchPaths) { $candidates = @($script:OpsDevWatchPaths) + $candidates }
    $seen = @{}
    $out = [System.Collections.ArrayList]@()
    foreach ($name in $candidates) {
        if ($seen[$name]) { continue }
        $p = Join-Path $root $name
        if (Test-Path $p) {
            [void]$out.Add($p)
            $seen[$name] = $true
        }
    }
    foreach ($df in @("Dockerfile", "src/Dockerfile")) {
        $p = Join-Path $root $df
        if ((Test-Path $p) -and -not $seen[$df]) {
            [void]$out.Add($p)
            $seen[$df] = $true
        }
    }
    return $out
}
