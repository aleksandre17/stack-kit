# Regenerate compose from project catalog via stack-kit package
$ErrorActionPreference = "Stop"
$PackageCompose = Join-Path $PSScriptRoot "build.py"
. (Join-Path $PSScriptRoot "..\lib\stack-kit-python.ps1")
$pyArgs = Get-StackKitPythonArgs
if (-not $pyArgs) {
    Write-Error "Python not found (tried py -3, python3, python)"
    exit 9009
}
Invoke-StackKitPythonExe $pyArgs $PackageCompose
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
