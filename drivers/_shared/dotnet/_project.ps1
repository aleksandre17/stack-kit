# .NET driver family - resolve the module's project file and declared options.
# Everything is read from modules.<id>.dotnet in the project manifest; nothing is assumed
# about a project name, a solution layout or a hosting product.

function Get-DotnetModuleOptions {
    param([Parameter(Mandatory = $true)][string]$ModuleId)
    $entry = Get-ModuleManifestEntry $ModuleId
    if ($entry -and $entry.PSObject.Properties["dotnet"]) { return $entry.dotnet }
    return [pscustomobject]@{}
}

function Resolve-DotnetProjectFile {
    param(
        [Parameter(Mandatory = $true)][string]$ModuleId,
        [Parameter(Mandatory = $true)][string]$ModPath
    )
    $opts = Get-DotnetModuleOptions $ModuleId
    if ($opts.PSObject.Properties["project"] -and $opts.project) {
        $declared = Join-Path $ModPath $opts.project
        if (-not (Test-Path $declared -PathType Leaf)) {
            throw "modules.$ModuleId.dotnet.project points to a missing file: $declared"
        }
        return (Resolve-Path $declared).Path
    }
    $found = @(Get-ChildItem -Path $ModPath -Filter *.csproj -File)
    if ($found.Count -eq 1) { return $found[0].FullName }
    if ($found.Count -eq 0) {
        throw "No *.csproj in $ModPath - set modules.$ModuleId.dotnet.project"
    }
    throw "Several *.csproj in $ModPath - set modules.$ModuleId.dotnet.project (found: $(($found.Name) -join ', '))"
}

function Get-DotnetOption {
    param(
        [Parameter(Mandatory = $true)][string]$ModuleId,
        [Parameter(Mandatory = $true)][string]$Name,
        $Default = $null
    )
    $opts = Get-DotnetModuleOptions $ModuleId
    if ($opts.PSObject.Properties[$Name] -and $null -ne $opts.$Name) { return $opts.$Name }
    return $Default
}

function Resolve-DotnetModuleTarget {
    # What a lifecycle step acts on: `dotnet.<Field>` (a project or solution, module-relative) when
    # declared, else the module's solution (`dotnet.solution`), else its project. A field declared
    # "" says the module has none: $null is returned and the caller says so.
    param(
        [Parameter(Mandatory = $true)][string]$ModuleId,
        [Parameter(Mandatory = $true)][string]$ModPath,
        [string]$Field = "solution"
    )
    $opts = Get-DotnetModuleOptions $ModuleId
    foreach ($name in @($Field, "solution") | Select-Object -Unique) {
        if ($opts.PSObject.Properties[$name]) {
            $rel = [string]$opts.$name
            if ($rel -eq "") { if ($name -eq $Field) { return $null } else { continue } }
            $path = Join-Path $ModPath $rel
            if (-not (Test-Path $path -PathType Leaf)) {
                throw "modules.$ModuleId.dotnet.$name points to a missing file: $path"
            }
            return (Resolve-Path $path).Path
        }
    }
    return Resolve-DotnetProjectFile -ModuleId $ModuleId -ModPath $ModPath
}

function Invoke-DotnetStep {
    # One lifecycle step: dotnet <verb> <target> [args], its exit code the step's.
    param([string]$Verb, [string]$Target, [string[]]$Rest = @())
    $argv = @($Verb, $Target) + $Rest
    Write-Host "  [$env:STACK_KIT_MODULE_ID $Verb] dotnet $($argv -join ' ')" -ForegroundColor Cyan
    & dotnet @argv | Out-Host
    return $LASTEXITCODE
}
