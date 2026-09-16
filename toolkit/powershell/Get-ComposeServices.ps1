# Parse services from compose via Docker (fallback: line parser)
function Get-ComposeServicesFromFile {
    param(
        [string]$ModuleRoot,
        [string]$ComposeFile = "docker-compose.yml",
        [string[]]$ExtraComposeFiles = @()
    )

    $composePath = Join-Path $ModuleRoot $ComposeFile
    if (-not (Test-Path $composePath)) { return @() }

    if (Get-Command docker -ErrorAction SilentlyContinue) {
        Push-Location $ModuleRoot
        try {
            $args = @("compose", "-f", $ComposeFile)
            foreach ($f in $ExtraComposeFiles) { $args += @("-f", $f) }
            $args += @("config", "--format", "json")
            $json = & docker @args 2>$null
            if ($LASTEXITCODE -eq 0 -and $json) {
                # Resolved model keeps container_name, build.context (absolute) and build.dockerfile.
                $model = ($json -join "`n") | ConvertFrom-Json
                return @($model.services.PSObject.Properties | ForEach-Object {
                    $svc = $_.Value
                    [PSCustomObject]@{
                        Name          = $_.Name
                        ContainerName = if ($svc.container_name) { $svc.container_name } else { $_.Name }
                        Context       = if ($svc.build -and $svc.build.context) { $svc.build.context } else { '.' }
                        Dockerfile    = if ($svc.build -and $svc.build.dockerfile) { $svc.build.dockerfile } else { 'Dockerfile' }
                    }
                })
            }
        } finally { Pop-Location }
    }

    # Fallback: legacy parser from ops toolkit
    $prev = $OpsComposeFile
    $script:OpsComposeFile = $ComposeFile
    try { $services = @(Get-DockerServices) } finally { $script:OpsComposeFile = $prev }
    # Overlays may override container_name (e.g. a dev overlay isolating from a running prod container).
    foreach ($extra in $ExtraComposeFiles) {
        if (-not (Test-Path (Join-Path $ModuleRoot $extra))) { continue }
        $script:OpsComposeFile = $extra
        try { $overrides = @(Get-DockerServices) } finally { $script:OpsComposeFile = $prev }
        foreach ($o in $overrides) {
            $target = $services | Where-Object { $_.Name -eq $o.Name } | Select-Object -First 1
            if ($target -and $o.ContainerName -ne $o.Name) { $target.ContainerName = $o.ContainerName }
        }
    }
    return $services
}
