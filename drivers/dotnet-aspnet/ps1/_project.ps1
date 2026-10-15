# dotnet-aspnet - resolve the module's project file and declared options.
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
