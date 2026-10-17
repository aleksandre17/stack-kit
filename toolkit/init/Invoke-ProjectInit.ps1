# stack-kit init — full project bootstrap (scaffold + seed secrets + compose-gen + checklist)
param(
    [string]$ProjectRoot = "",
    [string]$PackageRoot = "",
    [switch]$MinimalCatalog,
    [switch]$SkipComposeGen,
    [switch]$SkipSeed,
    [switch]$SkipNginxGen,
    [switch]$SkipGitIgnore,
    [switch]$ForceExamples
)

$ErrorActionPreference = "Stop"

if (-not $PackageRoot) {
    $PackageRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}
$ScaffoldRoot = Join-Path $PackageRoot "scaffold"
# One way to start the kit's Python, the CLI's own (lib/stack-kit-python.ps1).
. (Join-Path $PackageRoot "lib\stack-kit-python.ps1")

function Find-ProjectRoot {
    param([string]$Start)
    $dir = (Resolve-Path $Start -ErrorAction SilentlyContinue).Path
    if (-not $dir) { $dir = (Get-Location).Path }
    while ($dir) {
        if (Test-Path (Join-Path $dir "stack-kit.json")) { return $dir }
        $parent = Split-Path $dir -Parent
        if (-not $parent -or $parent -eq $dir) { break }
        $dir = $parent
    }
    $viaPkg = Split-Path (Split-Path $PackageRoot -Parent) -Parent
    if (Test-Path (Join-Path $viaPkg "stack-kit.json")) { return $viaPkg }
    return (Get-Location).Path
}

if (-not $ProjectRoot) {
    $ProjectRoot = Find-ProjectRoot -Start (Get-Location).Path
}
$ProjectRoot = (Resolve-Path $ProjectRoot).Path

function Write-Step([string]$msg) {
    Write-Host ""
    Write-Host "  ▸ $msg" -ForegroundColor Cyan
}

function Copy-IfMissing {
    param(
        [string]$ExampleRel,
        [string]$TargetRel,
        [switch]$Optional,
        [switch]$Force
    )
    $ex = Join-Path $ProjectRoot ($ExampleRel -replace '/', '\')
    $tg = Join-Path $ProjectRoot ($TargetRel -replace '/', '\')
    if (-not (Test-Path $ex)) {
        if (-not $Optional) { Write-Host "  [warn] missing example: $ExampleRel" -ForegroundColor Yellow }
        return
    }
    if ((Test-Path $tg) -and -not $Force) {
        Write-Host "  [skip] $TargetRel (exists)" -ForegroundColor DarkGray
        return
    }
    $parent = Split-Path $tg -Parent
    if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    Copy-Item -LiteralPath $ex -Destination $tg -Force
    Write-Host "  [OK]   $TargetRel  ←  $ExampleRel" -ForegroundColor Green
}

function Merge-GitIgnore {
    $example = Join-Path $ScaffoldRoot ".gitignore.example"
    $target = Join-Path $ProjectRoot ".gitignore"
    if (-not (Test-Path $example)) { return }
    $lines = Get-Content $example -Encoding UTF8 | Where-Object { $_ -notmatch '^\s*#' -and $_.Trim() -ne "" }
    $existing = @()
    if (Test-Path $target) { $existing = Get-Content $target -Encoding UTF8 -Raw }
    $added = 0
    $buf = [System.Collections.Generic.List[string]]::new()
    if (Test-Path $target) {
        foreach ($l in (Get-Content $target -Encoding UTF8)) { [void]$buf.Add($l) }
    }
    foreach ($line in $lines) {
        if ($existing -match [regex]::Escape($line)) { continue }
        [void]$buf.Add($line)
        $added++
    }
    if ($added -gt 0) {
        if ($buf.Count -gt 0 -and $buf[-1] -ne "") { [void]$buf.Add("") }
        if (-not (Test-Path $target)) {
            [void]$buf.Insert(0, "# stack-kit init")
            [void]$buf.Insert(1, "")
        }
        Set-Content -Path $target -Value $buf -Encoding UTF8
        Write-Host "  [OK]   .gitignore (+$added lines from scaffold)" -ForegroundColor Green
    } else {
        Write-Host "  [skip] .gitignore (already has scaffold rules)" -ForegroundColor DarkGray
    }
}

function Show-Checklist {
    param([string]$Root)
    $env:STACK_KIT_PROJECT_ROOT = $Root
    . (Join-Path $PackageRoot "lib\project.ps1")
    . (Join-Path $PackageRoot "lib\modules.ps1")

    Write-Host ""
    Write-Host "  ═══════════════════════════════════════════════════════" -ForegroundColor DarkCyan
    Write-Host "  Fill in (search for YOUR_ / example.com / empty values)" -ForegroundColor Yellow
    Write-Host "  ═══════════════════════════════════════════════════════" -ForegroundColor DarkCyan

    # The host's own modules name what is left to fill in, and the CI it already had is named beside
    # the one ci-gen wrote (lib/init_checklist.py: one reading, tested).
    $py = Get-StackKitPythonArgs
    if ($py) {
        $env:PYTHONPATH = $PackageRoot
        Invoke-StackKitPythonExe $py "-B" (Join-Path $PackageRoot "lib\init_checklist.py") | ForEach-Object {
            $color = if ($_ -match '^\s*\[x\]') { "Green" } elseif ($_ -match '^\s*\[!\]') { "Magenta" } elseif ($_ -match 'create / seed') { "Red" } else { "Yellow" }
            Write-Host $_ -ForegroundColor $color
        }
    }

    Write-Host ""
    Write-Host "  Commands:" -ForegroundColor Cyan
    Write-Host "    .\tools\stack-kit.ps1 compose-gen    # after catalog edits"
    Write-Host "    .\tools\stack-kit.ps1 stack up -d --build"
    Write-Host "    .\tools\stack-kit.ps1 mod <moduleId> check   # or a module's cli alias"
    Write-Host "  Docs: kits\stack-kit\docs\ADOPT.md"
    Write-Host ""
}

Write-Host ""
Write-Host "  stack-kit init → $ProjectRoot" -ForegroundColor White
Write-Host "  package: $PackageRoot" -ForegroundColor DarkGray

# ── 1. The points init lays down (config/extension-points.json, required_by init) ──
# The scaffold is the template store of the extension points; init is `extend` of every point
# init requires, then of each infra service the manifest selects. Nothing is overwritten.
Write-Step "Extension points required by init (scaffold, manifest, launchers, infra services)"
if ($MinimalCatalog) {
    $catDst = Join-Path $ProjectRoot "ops\compose\catalog.json"
    if (-not (Test-Path $catDst)) {
        # placed for this host: its modules' paths, else its layout profile's, else apps/<tier>
        $pyCat = Get-StackKitPythonArgs
        if (-not $pyCat) { Write-Host "  [ERROR] Python 3 is required" -ForegroundColor Red; exit 9009 }
        Invoke-StackKitPythonExe $pyCat "-B" "-c" "import sys; sys.path.insert(0, sys.argv[1]); from lib import extend; extend.copy_placed(sys.argv[2], sys.argv[3], sys.argv[4])" $PackageRoot "scaffold/ops/compose/catalog.minimal.json" $ProjectRoot "ops/compose/catalog.json"
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        Write-Host "  [OK]   ops/compose/catalog.json (minimal)" -ForegroundColor Green
    }
}
$pyInit = Get-StackKitPythonArgs
if (-not $pyInit) { Write-Host "  [ERROR] Python 3 is required" -ForegroundColor Red; exit 9009 }
Invoke-StackKitPythonExe $pyInit "-B" (Join-Path $PackageRoot "cli\stack_kit.py") "extend" "--init" "--root" $ProjectRoot
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# The manifest now exists: the kit's manifest readers answer for this project from here on.
$env:STACK_KIT_PROJECT_ROOT = $ProjectRoot
$env:STACK_KIT_KIT_ROOT = $PackageRoot
. (Join-Path $PackageRoot "lib\project.ps1")

# ── 3. Seed ops/config (manifest modules via ci_prepare) ─────────
if (-not $SkipSeed) {
    Write-Step "Seed ops/config (manifest modules)"
    $py = Get-StackKitPythonArgs
    if ($py) {
        $env:PYTHONPATH = $PackageRoot
        $seedPy = Join-Path $PackageRoot "lib\ci_prepare.py"
        Invoke-StackKitPythonExe $py $seedPy
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  [warn] ci_prepare seed failed" -ForegroundColor Yellow
        }
    }
    # The ui module's nginx env, where init laid its example -- the same reading the checklist names
    # (lib/init_checklist.py), never the scaffold's folder names.
    $py = Get-StackKitPythonArgs
    if ($py) {
        $env:PYTHONPATH = $PackageRoot
        $pair = Invoke-StackKitPythonExe $py "-B" (Join-Path $PackageRoot "lib\init_checklist.py") "--nginx"
        if ($pair) {
            $nginxEx, $nginxTg = ($pair | Select-Object -First 1) -split '\|'
            Copy-IfMissing -ExampleRel ($nginxEx -replace '/', '\') -TargetRel ($nginxTg -replace '/', '\') -Optional:$true -Force:$ForceExamples
        }
    }
}

# ── 4. .gitignore merge ──────────────────────────────────────────
if (-not $SkipGitIgnore) {
    Write-Step "Merge .gitignore rules"
    Merge-GitIgnore
}

# ── 5. compose-gen ───────────────────────────────────────────────
$env:STACK_KIT_PROJECT_ROOT = $ProjectRoot
$env:STACK_KIT_KIT_ROOT = $PackageRoot

if (-not $SkipComposeGen) {
    Write-Step "Generate docker-compose files (compose-gen)"
    $py = Get-StackKitPythonArgs
    if (-not $py) {
        Write-Host "  [warn] Python not found — run later: stack-kit compose-gen" -ForegroundColor Yellow
    } else {
        $buildPy = Join-Path $PackageRoot "compose\build.py"
        Invoke-StackKitPythonExe $py $buildPy
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  [warn] compose-gen failed (fix catalog.json, then re-run)" -ForegroundColor Yellow
        } else {
            Write-Host "  [OK]   compose files generated" -ForegroundColor Green
        }
    }
}

# ── 6. VS Code Run and Debug (.vscode) ───────────────────────────
Write-Step "VS Code launch.json + tasks.json (vscode-gen)"
$py = Get-StackKitPythonArgs
if ($py) {
    $vscodePy = Join-Path $PackageRoot "lib\vscode_gen.py"
    $env:PYTHONPATH = $PackageRoot
    Invoke-StackKitPythonExe $py $vscodePy
    if ($LASTEXITCODE -eq 0) { Write-Host "  [OK]   .vscode (missing files only; use stack-kit vscode-gen --force)" -ForegroundColor Green }
} else {
    Write-Host "  [warn] Python not found — run: stack-kit vscode-gen" -ForegroundColor Yellow
}

# ── 6b. CI workflow (ci-gen) ─────────────────────────────────────
Write-Step "CI workflow: a job per module, lint/build/test through the launcher (ci-gen)"
$py = Get-StackKitPythonArgs
if ($py) {
    $env:PYTHONPATH = $PackageRoot
    Invoke-StackKitPythonExe $py (Join-Path $PackageRoot "lib\ci_gen.py")
    if ($LASTEXITCODE -ne 0) { Write-Host "  [warn] ci-gen failed - run: stack-kit ci-gen" -ForegroundColor Yellow }
} else {
    Write-Host "  [warn] Python not found - run: stack-kit ci-gen" -ForegroundColor Yellow
}

# ── 7. nginx-gen (optional) ──────────────────────────────────────
if (-not $SkipNginxGen) {
    $mf = Join-Path $ProjectRoot "stack-kit.json"
    if (Test-Path $mf) {
        $manifest = Get-Content $mf -Raw | ConvertFrom-Json
        $tpl = $manifest.adapters.nginx.template
        if ($tpl -and (Test-Path (Join-Path $ProjectRoot ($tpl -replace '/', '\')))) {
            Write-Step "Generate nginx.conf (nginx-gen)"
            $py = Get-StackKitPythonArgs
            if ($py) {
                $render = Join-Path $PackageRoot "adapters\render_nginx.py"
                Invoke-StackKitPythonExe $py $render
                if ($LASTEXITCODE -eq 0) { Write-Host "  [OK]   nginx.conf" -ForegroundColor Green }
            }
        }
    }
}

Show-Checklist -Root $ProjectRoot
exit 0
