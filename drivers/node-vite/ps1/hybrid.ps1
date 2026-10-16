# node-vite - launch step, dot-sourced by toolkit/hybrid/Invoke-HybridRun.ps1 after the module's
# run environment was imported: the module's npm script (`hybrid.npmScript`, default `dev`).
# In scope from the caller: $ModuleId, $modPath, $root, $PackageRoot.

$npmScript = Get-ModuleField $ModuleId 'debug.npmScript', 'hybrid.npmScript'
if (-not $npmScript) { $npmScript = "dev" }

npm run $npmScript
exit $LASTEXITCODE
