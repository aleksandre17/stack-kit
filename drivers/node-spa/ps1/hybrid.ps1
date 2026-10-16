# node-spa - launch step, dot-sourced by toolkit/hybrid/Invoke-HybridRun.ps1 after the module's
# run environment was imported: the package's `start` script (or the module's
# node.scripts.start), through the kit's package-script runner.
# In scope from the caller: $ModuleId, $modPath, $root, $PackageRoot.

& (Join-Path $PackageRoot "drivers\_shared\package-scripts\Invoke-PackageScript.ps1") -ModuleId $ModuleId -Step "start"
exit $LASTEXITCODE
