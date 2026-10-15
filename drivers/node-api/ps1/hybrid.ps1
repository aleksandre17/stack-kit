# node-api - launch step, dot-sourced by toolkit/hybrid/Invoke-HybridRun.ps1 after the module's
# run environment was imported. A pnpm-workspace Node service: the module's dev/start script runs
# through pnpm so workspace dependencies resolve; npm when pnpm is not on PATH.
# In scope from the caller: $ModuleId, $modPath, $root, $PackageRoot.

$npmScript = Get-ModuleNpmScript $ModuleId
if (-not $npmScript) { $npmScript = "dev" }

if (Get-Command pnpm -ErrorAction SilentlyContinue) {
    pnpm run $npmScript
} else {
    Write-Host "[hybrid] pnpm not on PATH - falling back to npm run $npmScript" -ForegroundColor Yellow
    npm run $npmScript
}
exit $LASTEXITCODE
