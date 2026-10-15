# Dev modes verification — package + consumer (no long-running servers)
# Usage: .\kits\stack-kit\scripts\dev-modes-verify.ps1 [-SkipDocker] [-SkipGradle] [-SkipNpm]
param(
    [switch]$SkipDocker,
    [switch]$SkipGradle,
    [switch]$SkipNpm
)

$ErrorActionPreference = "Stop"
$Kit = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Root = if ($env:STACK_KIT_PROJECT_ROOT) { $env:STACK_KIT_PROJECT_ROOT } else {
    (Resolve-Path (Join-Path $Kit "..\..")).Path
}
$env:STACK_KIT_KIT_ROOT = $Kit
$env:STACK_KIT_PROJECT_ROOT = $Root
$env:PYTHONPATH = $Kit
function Get-PythonCmd {
    foreach ($c in @("python", "py", "python3")) {
        if (Get-Command $c -ErrorAction SilentlyContinue) {
            if ($c -eq "py") { return @("py", "-3") }
            return @($c)
        }
    }
    return $null
}
$pyCmd = Get-PythonCmd
if (-not $pyCmd) { Write-Host "  [FAIL] Python not found"; exit 1 }

$results = [System.Collections.Generic.List[object]]::new()

function Add-Result($Name, $Ok, $Detail) {
    $script:results.Add([pscustomobject]@{ Name = $Name; Ok = $Ok; Detail = $Detail })
    $color = if ($Ok) { "Green" } else { "Red" }
    $mark = if ($Ok) { "PASS" } else { "FAIL" }
    Write-Host "  [$mark] $Name" -ForegroundColor $color
    if ($Detail) { Write-Host "         $Detail" -ForegroundColor DarkGray }
}

Write-Host ""
Write-Host "=== stack-kit dev-modes verify ===" -ForegroundColor Cyan
Write-Host "  root: $Root"
Write-Host "  kit:  $Kit"
Write-Host ""

# 1 Package pytest
Write-Host "--- 1. Package tests (pytest) ---" -ForegroundColor Cyan
Push-Location $Kit
try {
    $out = & @pyCmd -m pytest tests -q --tb=no 2>&1 | Out-String
    $ok = $LASTEXITCODE -eq 0
    Add-Result "pytest (full kit)" $ok ($out.Trim().Split("`n")[-1])
} finally { Pop-Location }

# 2 Manifest validate
Write-Host "--- 2. Manifest validate ---" -ForegroundColor Cyan
$valOut = & @pyCmd (Join-Path $Kit "lib\validate_manifest.py") 2>&1 | Out-String
Add-Result "stack-kit validate" ($LASTEXITCODE -eq 0) $valOut.Trim()

# 3 DEV-MODES doc + vscode files
Write-Host "--- 3. Docs + .vscode ---" -ForegroundColor Cyan
Add-Result "DEV-MODES.md" (Test-Path (Join-Path $Kit "docs\DEV-MODES.md")) ""
$launch = Join-Path $Root ".vscode\launch.json"
$tasks = Join-Path $Root ".vscode\tasks.json"
Add-Result ".vscode/launch.json" (Test-Path $launch) $launch
Add-Result ".vscode/tasks.json" (Test-Path $tasks) $tasks

# 4 Mode 1 prerequisites (host)
Write-Host "--- 4. Mode 1 local host (prereqs) ---" -ForegroundColor Cyan
$mf = Get-Content (Join-Path $Root "stack-kit.json") -Raw | ConvertFrom-Json
$fePath = Join-Path $Root ($mf.modules.frontend.path -replace '/', '\')
$beModId = [string]$mf.cli.aliases.be
$bePath = Join-Path $Root ($mf.modules.$beModId.path -replace '/', '\')
Add-Result "frontend path exists" (Test-Path $fePath) $fePath
Add-Result "backend path exists" (Test-Path $bePath) $bePath
if (-not $SkipNpm) {
    $npmOk = (Get-Command npm -EA SilentlyContinue) -and (Test-Path (Join-Path $fePath "package.json"))
    Add-Result "npm + package.json (UI)" $npmOk ""
}
if (-not $SkipGradle) {
    $gw = Join-Path $bePath "gradlew.bat"
    Add-Result "gradlew.bat (API)" (Test-Path $gw) $gw
}

# 5 Mode 2 compose (docker)
Write-Host "--- 5. Mode 2 local Docker ---" -ForegroundColor Cyan
$stackKit = Join-Path $Root "tools\stack-kit.ps1"
Add-Result "tools/stack-kit.ps1" (Test-Path $stackKit) ""
if (-not $SkipDocker) {
    $dockerOk = $false
    $dockerDetail = "docker not in PATH"
    if (Get-Command docker -EA SilentlyContinue) {
        $dv = docker version --format "{{.Server.Version}}" 2>&1
        $dockerOk = $LASTEXITCODE -eq 0
        $dockerDetail = if ($dockerOk) { "server $dv" } else { $dv }
    }
    Add-Result "docker daemon" $dockerOk $dockerDetail
    if ($dockerOk -and (Test-Path $stackKit)) {
        & $stackKit fe check 2>&1 | Out-Null
        Add-Result "stack-kit fe check" ($LASTEXITCODE -eq 0) ""
        & $stackKit be check 2>&1 | Out-Null
        Add-Result "stack-kit be check" ($LASTEXITCODE -eq 0) ""
    }
} else {
    Add-Result "docker checks" $true "skipped (-SkipDocker)"
}

# 6 Mode 3 remote (config only - no SSH)
Write-Host "--- 6. Mode 3 remote (config smoke) ---" -ForegroundColor Cyan
$secretsRoot = Join-Path $Root ($mf.secrets -replace '/', '\')
$beMod = $mf.modules.$beModId
$feMod = $mf.modules.frontend
$beDeploy = Join-Path $secretsRoot "$($beMod.secretsModule)\.env.deploy"
$feDeploy = Join-Path $secretsRoot "$($feMod.secretsModule)\.env.deploy"
$structured = $false
if (Test-Path $beDeploy) {
    $t = Get-Content $beDeploy -Raw
    $structured = $t -match "DEPLOY_LAYOUT=structured"
}
Add-Result "backend DEPLOY_LAYOUT=structured" $structured $beDeploy
Add-Result "frontend .env.deploy exists" (Test-Path $feDeploy) $feDeploy
Push-Location $Kit
$inline = @"
import sys
sys.path.insert(0, r'$Kit')
from lib.deploy_paths import resolve_backend_deploy_path
from lib.modules import module_by_role
from lib.project_context import ProjectContext
ctx = ProjectContext.discover()
api_id = module_by_role(ctx.manifest, 'api', 0)
assert api_id, 'no api module'
deploy = ctx.secrets_module_dir(api_id) / '.env.deploy'
assert deploy.is_file(), deploy
assert 'DEPLOY_LAYOUT=structured' in deploy.read_text(encoding='utf-8')
names = ctx.compose_service_names()
api = names['api']
base = '/home/example/my-app/' + ctx.module_path(api_id).name
assert 'runtime' in resolve_backend_deploy_path(base=base, container_name=api, kind='runtime', layout='structured')
print('OK module-ops smoke')
"@
& @pyCmd -c $inline 2>&1 | Out-Null
Add-Result "module-ops-smoke" ($LASTEXITCODE -eq 0) ""
Pop-Location

# Summary
Write-Host ""
$fail = @($results | Where-Object { -not $_.Ok })
$pass = @($results | Where-Object { $_.Ok })
Write-Host "=== Summary: $($pass.Count) passed, $($fail.Count) failed ===" -ForegroundColor $(if ($fail.Count) { "Red" } else { "Green" })
if ($fail.Count) {
    $fail | ForEach-Object { Write-Host "  FAIL: $($_.Name) - $($_.Detail)" -ForegroundColor Red }
    exit 1
}
Write-Host "  All verification steps passed." -ForegroundColor Green
Write-Host "  Note: Mode 1/2 runtime (npm dev, bootRun, compose up) not started - use manual or CI integration-stack for E2E." -ForegroundColor DarkYellow
exit 0
