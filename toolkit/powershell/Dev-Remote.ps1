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
    foreach ($e in $excludes) {
        $x = $e.Trim().TrimEnd('/')
        if ($x) { "--exclude=$x" }
    }
}

function Get-DevComposeFileArgs {
    param([ValidateSet("dev", "prod")][string]$Environment = "dev")
    if ($script:OpsDevComposeDevFiles -and $Environment -eq "dev") {
        $files = @("docker-compose.yml") + @($script:OpsDevComposeDevFiles)
        return ($files | ForEach-Object { "-f $_" }) -join " "
    }
    if ($Environment -eq "dev") {
        return "-f docker-compose.yml -f docker-compose.override.yml"
    }
    return "-f docker-compose.yml -f docker-compose.prod.yml"
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
