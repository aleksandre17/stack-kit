# Deploy path resolution (structured layout) — dot-source after _common.ps1 init

function Get-DeployPathBase {
    $base = Get-EnvValue "DEPLOY_PATH"
    if (-not $base) {
        # The folder a module without its own DEPLOY_PATH inherits from: declared, else the primary API's.
        $deployBaseModule = Get-KitContextValue "deployBaseSecretsFolder"
        if ($deployBaseModule -and $OpsSecretsModule -and $OpsSecretsModule -ne $deployBaseModule) {
            $base = Get-SecretsEnvValue -Module $deployBaseModule -Key "DEPLOY_PATH"
        }
    }
    if (-not $base -and $script:SERVER_BASE -and $OpsSecretsModule) {
        $base = Get-DefaultRemoteDeployPathBase -SecretsFolder $OpsSecretsModule
    }
    if ($base) { return $base.Trim().TrimEnd('/') }
    return $null
}

function Get-DeployLayout {
    $layout = Get-EnvValue "DEPLOY_LAYOUT"
    if ($layout -in @("structured", "flat", "legacy")) { return $layout }
    return "structured"
}

function Get-DeployPathMode {
    $m = Get-EnvValue "DEPLOY_PATH_MODE"
    if ($m -in @("base", "full")) { return $m }
    return "base"
}

function Resolve-ModuleDeployPath {
    param(
        [Parameter(Mandatory = $true)][string]$ContainerName,
        [Parameter(Mandatory = $true)][ValidateSet("static", "compose-dev", "compose-prod")][string]$Kind
    )
    $base = Get-DeployPathBase
    if (-not $base) { throw "DEPLOY_PATH or DEPLOY_SERVER_BASE required in secrets" }

    $layout = Get-DeployLayout
    $pathMode = Get-DeployPathMode

    if ($pathMode -eq "full") {
        if ($base -match "/$([regex]::Escape($ContainerName))$") { return $base }
        return $base
    }

    if ($layout -eq "structured") {
        switch ($Kind) {
            "static" { return "$base/static/$ContainerName" }
            "compose-dev" { return "$base/compose/dev/$ContainerName" }
            "compose-prod" { return "$base/compose/prod/$ContainerName" }
        }
    }

    # flat / legacy: single tree per service under base
    if ($base -match "/$([regex]::Escape($ContainerName))$") { return $base }
    return "$base/$ContainerName"
}

function Get-DeployPathCandidates {
    param([Parameter(Mandatory = $true)][string]$ContainerName)
    $base = Get-DeployPathBase
    if (-not $base) { return @() }
    @(
        "$base/static/$ContainerName",
        "$base/compose/prod/$ContainerName",
        "$base/compose/dev/$ContainerName",
        "$base/$ContainerName"
    )
}

function Set-DeployPathForMode {
    param([Parameter(Mandatory = $true)][ValidateSet("static", "compose-dev", "compose-prod")][string]$Kind)
    $script:DEPLOY_PATH = Resolve-ModuleDeployPath -ContainerName $script:APP_NAME -Kind $Kind
    $script:DEPLOY_KIND = $Kind
}

function Update-DeployPathFromServer {
    if (-not $script:SERVER) { return }
    $manifestPath = ""
    # The current marker first; one an older deploy left is still found, with a notice (ADR-001).
    $id = Get-KitIdentity
    :found foreach ($candidate in (Get-DeployPathCandidates -ContainerName $script:APP_NAME)) {
        foreach ($marker in @($id.deployMarker, $id.legacyDeployMarker) | Where-Object { $_ }) {
            $check = Invoke-SSHCapture "test -f '$candidate/$marker' && echo '$candidate'"
            $line = ($check | Where-Object { $_ -match '\S' } | Select-Object -Last 1)
            if ($line -and $line.Trim()) {
                $script:DEPLOY_PATH = $line.Trim()
                $manifestPath = "$($script:DEPLOY_PATH)/$marker"
                if ($marker -ne $id.deployMarker) { Write-KitDeprecation $marker $id.deployMarker }
                break found
            }
        }
    }
    if (-not $manifestPath) {
        foreach ($candidate in (Get-DeployPathCandidates -ContainerName $script:APP_NAME)) {
            $check = Invoke-SSHCapture @"
if [ -f '$candidate/dist/index.html' ] || [ -f '$candidate/docker-compose.yml' ]; then echo '$candidate'; fi
"@
            $line = ($check | Where-Object { $_ -match '\S' } | Select-Object -Last 1)
            if ($line -and $line.Trim()) {
                $script:DEPLOY_PATH = $line.Trim()
                break
            }
        }
    }
}

function Get-SecretsEnvValueForProfile {
    param(
        [string]$Module,
        [Parameter(Mandatory = $true)][ValidateSet("dev", "prod")][string]$Profile,
        [string]$Key,
        [string]$Default = $null
    )
    $dir = Get-SecretsModuleDir -Module $Module
    $file = Join-Path $dir ".env.$Profile"
    if (-not (Test-Path $file)) {
        return Get-SecretsEnvValue -Module $Module -Key $Key -Default $Default
    }
    foreach ($line in Get-Content $file) {
        if ($line -match '^\s*#' -or $line -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') { continue }
        if ($Matches[1] -eq $Key) {
            $v = $Matches[2].Trim().Trim('"').Trim("'")
            if ($v) { return $v }
        }
    }
    return $Default
}

function Get-ViteApiUrlForEnvironment {
    param([ValidateSet("dev", "prod")][string]$Environment)
    $v = Get-SecretsEnvValueForProfile -Module $OpsSecretsModule -Profile $Environment -Key "VITE_API_URL"
    if ($v) { return $v }
    return Get-EnvValue "VITE_API_URL"
}

function Invoke-NpmBuildForEnvironment {
    param(
        [ValidateSet("dev", "prod")][string]$Environment,
        [string]$LogFile = $script:LOG_FILE
    )
    Push-Location $script:BUILD_CONTEXT
    try {
        $env:VITE_API_URL = Get-ViteApiUrlForEnvironment -Environment $Environment
        Log "npm build (profile: $Environment, VITE_API_URL=$($env:VITE_API_URL))" "INFO"
        if ($Environment -eq "dev") {
            if (Test-Path (Join-Path $script:BUILD_CONTEXT "package.json")) {
                $pkg = Get-Content (Join-Path $script:BUILD_CONTEXT "package.json") -Raw | ConvertFrom-Json
                if ($pkg.scripts.'build:dev') {
                    npm run build:dev 2>&1 | ForEach-Object { Write-NpmLog $_ $LogFile }
                } else {
                    npx vite build --mode dev 2>&1 | ForEach-Object { Write-NpmLog $_ $LogFile }
                }
            }
        } else {
            npm run build 2>&1 | ForEach-Object { Write-NpmLog $_ $LogFile }
        }
        return $LASTEXITCODE
    } finally {
        Remove-Item Env:VITE_API_URL -ErrorAction SilentlyContinue
        Pop-Location
    }
}

function Write-NpmLog {
    param([string]$Line, [string]$LogFile)
    if ($LogFile) { Add-Content -Path $LogFile -Value "[npm] $Line" -Encoding UTF8 }
    Write-Host "[npm] $Line" -ForegroundColor DarkGray
}

# Build dist, upload static bundle (+ nginx/runtime), optional nginx reload on server.
function Invoke-FeStaticPublishCycle {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("dev", "prod")][string]$Environment,
        [string]$LogFile = $script:LOG_FILE,
        [switch]$ReloadNginx,
        [ValidateSet("dist", "sync")][string]$DeployMode = "sync"
    )
    $viteUrl = Get-ViteApiUrlForEnvironment -Environment $Environment
    $exitCode = Invoke-NpmBuildForEnvironment -Environment $Environment -LogFile $LogFile
    if ($exitCode -ne 0) { return $exitCode }

    $distDir = Join-Path $script:BUILD_CONTEXT "dist"
    @{ VITE_API_URL = $viteUrl } | ConvertTo-Json | Set-Content (Join-Path $distDir "config.json") -Encoding UTF8
    Sync-StaticArtifactsToServer -DistDir $distDir -IncludeNginx -WriteManifest -Environment $Environment -DeployMode $DeployMode

    if ($ReloadNginx) {
        $rc = Invoke-SSH "docker exec $($script:APP_NAME) nginx -s reload 2>/dev/null || docker restart $($script:APP_NAME)"
        if ($rc -eq 0) { Log "Nginx reload OK" "OK" } else { Log "Reload skipped (container may be down)" "WARN" }
    }
    return 0
}

function Write-RemoteDeployManifest {
    param(
        [ValidateSet("dev", "prod")][string]$Environment,
        [ValidateSet("local", "dist", "remote", "sync", "dev-bootstrap", "dev-sync")][string]$DeployMode,
        [ValidateSet("static", "compose-dev", "compose-prod")][string]$Kind
    )
    $manifest = @{
        version     = 1
        module      = $OpsSecretsModule
        service     = $script:APP_NAME
        deployMode  = $DeployMode
        kind        = $Kind
        environment = $Environment
        viteApiUrl  = Get-ViteApiUrlForEnvironment -Environment $Environment
        deployPath  = $script:DEPLOY_PATH
        updatedAt   = (Get-Date).ToUniversalTime().ToString("o")
    } | ConvertTo-Json -Compress
    $local = Join-Path $env:TEMP "stack-kit-deploy-manifest.json"
    Set-Content -Path $local -Value $manifest -Encoding UTF8 -NoNewline
    $null = & ssh @(Get-StackKitSshExtraArgs) $script:SERVER "mkdir -p $($script:DEPLOY_PATH)"
    $rc = Invoke-SCP -Source $local -Dest "$($script:DEPLOY_PATH)/$((Get-KitIdentity).deployMarker)"
    Remove-Item $local -ErrorAction SilentlyContinue
    if ($rc -ne 0) { Log "manifest upload failed (non-fatal)" "WARN" }
}

function Publish-RemoteEnvFiles {
    param(
        [ValidateSet("dev", "prod")][string]$Environment
    )
    $bundle = Join-Path $env:TEMP "stack-kit-fe-stack-$Environment.env"
    $lines = [System.Collections.ArrayList]@()
    [void]$lines.Add("# Generated for remote compose - stack-kit deploy")
    [void]$lines.Add("STACK_KIT_ENVIRONMENT=$Environment")
    foreach ($f in (Get-SecretsEnvFiles -Module $OpsSecretsModule -Profile $Environment)) {
        [void]$lines.Add("")
        [void]$lines.Add("# from $f")
        Get-Content $f | ForEach-Object { [void]$lines.Add($_) }
    }
    $root = Get-MonorepoRoot
    $deployEnv = Join-Path (Get-SecretsRoot) "deploy.env"
    if (Test-Path $deployEnv) {
        [void]$lines.Add("")
        [void]$lines.Add("# from deploy.env")
        Get-Content $deployEnv | ForEach-Object { [void]$lines.Add($_) }
    }
    $lines | Set-Content -Path $bundle -Encoding UTF8
    $remoteName = ".env.$Environment"
    $rc = Invoke-SCP -Source $bundle -Dest "$($script:DEPLOY_PATH)/$remoteName"
    Remove-Item $bundle -ErrorAction SilentlyContinue
    if ($rc -ne 0) { throw "Failed to upload $remoteName to server" }
    return $remoteName
}

function Sync-StaticArtifactsToServer {
    param(
        [string]$DistDir,
        [switch]$IncludeNginx,
        [switch]$WriteManifest,
        [ValidateSet("dev", "prod")][string]$Environment,
        [ValidateSet("dist", "sync")][string]$DeployMode
    )
    & ssh @(Get-StackKitSshExtraArgs) $script:SERVER "mkdir -p $($script:DEPLOY_PATH)/dist" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "mkdir on server failed" }

    $rc = Invoke-SCP -Source $DistDir -Dest "$($script:DEPLOY_PATH)/" -Recurse
    if ($rc -ne 0) { throw "scp dist failed" }

    if ($IncludeNginx) {
        Invoke-NginxGen
        $rc = Invoke-SCP -Source (Join-Path $script:ROOT "nginx.conf") -Dest $script:DEPLOY_PATH
        if ($rc -ne 0) { throw "scp nginx.conf failed" }
    }

    $runtime = @{
        VITE_API_URL  = Get-ViteApiUrlForEnvironment -Environment $Environment
        environment   = $Environment
        deployedAt    = (Get-Date).ToUniversalTime().ToString("o")
    } | ConvertTo-Json
    $rtLocal = Join-Path $env:TEMP "stack-kit-runtime.json"
    Set-Content -Path $rtLocal -Value $runtime -Encoding UTF8
    $null = Invoke-SCP -Source $rtLocal -Dest "$($script:DEPLOY_PATH)/.env.runtime.json"
    Remove-Item $rtLocal -ErrorAction SilentlyContinue

    & ssh @(Get-StackKitSshExtraArgs) $script:SERVER "chmod -R 755 $($script:DEPLOY_PATH)/dist" | Out-Null

    if ($WriteManifest) {
        Write-RemoteDeployManifest -Environment $Environment -DeployMode $DeployMode -Kind "static"
    }
}

# Requires Invoke-NginxGen from deploy.ps1 scope or define stub
function Get-StackKitPythonArgs {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -c "import sys" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { return @("py", "-3") }
    }
    foreach ($candidate in @("python", "python3")) {
        if (-not (Get-Command $candidate -ErrorAction SilentlyContinue)) { continue }
        & $candidate -c "import sys" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { return @($candidate) }
    }
    return $null
}

function Invoke-NginxGen {
    $py = Join-Path $env:STACK_KIT_KIT_ROOT "adapters\render_nginx.py"
    if (-not (Test-Path $py)) {
        Log "render_nginx.py missing - using existing nginx.conf" "WARN"
        return
    }
    $pyArgs = Get-StackKitPythonArgs
    if (-not $pyArgs) {
        Log "Python not found - using existing nginx.conf" "WARN"
        return
    }
    $env:STACK_KIT_PROJECT_ROOT = Get-MonorepoRoot
    if ($pyArgs.Count -gt 1) {
        & $pyArgs[0] $pyArgs[1] $py
    } else {
        & $pyArgs[0] $py
    }
    if ($LASTEXITCODE -ne 0) { Log "nginx-gen FAILED" "ERROR"; exit 1 }
    Log "nginx.conf rendered from secrets" "OK"
}
