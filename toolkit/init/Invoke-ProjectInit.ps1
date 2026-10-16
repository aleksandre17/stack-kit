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

    # Where deploys go is declared in the targets file (`deploy.targets`), never an env file.
    $checks = @()
    foreach ($mid in Get-ProjectModules) {
        $role = Get-ModuleRole $mid
        $sm = Get-ModuleSecretsFolder $mid
        $hints = switch ($role) {
            "ui" { @("VITE_API_URL") }
            "api" { @("GEMINI", "GCP", "API_KEY") }
            "worker" { @("API_INTERNAL_URL") }
            default { @() }
        }
        $checks += @{ File = "$(Get-SecretsConfigRel)/$sm/.env.dev" -replace '/', '\'; Hints = $hints }
        $checks += @{ File = "$(Get-SecretsConfigRel)/$sm/.env.prod" -replace '/', '\'; Hints = $hints }
    }
    $uiMod = Get-ModuleIdByRole "ui"
    if ($uiMod) {
        $nginxTg = (Get-ManifestField "adapters.nginx.env") -replace '/', '\'
        if ($nginxTg) { $checks += @{ File = $nginxTg; Hints = @("NGINX_FRAME_ANCESTORS") } }
    }

    foreach ($c in $checks) {
        $path = Join-Path $Root ($c.File -replace '/', '\')
        if (-not (Test-Path $path)) {
            Write-Host "  [ ] $($c.File) — create / seed" -ForegroundColor Red
            continue
        }
        $raw = Get-Content $path -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
        $todo = $false
        if ($raw -match 'YOUR_|example\.com|CHANGEME|user@YOUR') { $todo = $true }
        $color = if ($todo) { "Yellow" } else { "Green" }
        $mark = if ($todo) { "[ ]" } else { "[✓]" }
        Write-Host "  $mark $($c.File)" -ForegroundColor $color
    }

    Write-Host ""
    Write-Host "  Commands:" -ForegroundColor Cyan
    Write-Host "    .\tools\stack-kit.ps1 compose-gen    # after catalog edits"
    Write-Host "    .\tools\stack-kit.ps1 stack up -d --build"
    Write-Host "    .\tools\stack-kit.ps1 mod <moduleId> check   # or cli aliases (fe, be, ui, api)"
    Write-Host "  Docs: kits\stack-kit\docs\ADOPT.md"
    Write-Host ""
}

Write-Host ""
Write-Host "  stack-kit init → $ProjectRoot" -ForegroundColor White
Write-Host "  package: $PackageRoot" -ForegroundColor DarkGray

# ── 1. Scaffold tree ─────────────────────────────────────────────
Write-Step "Scaffold (apps/, ops/, tools shim, manifest)"
$applyArgs = @{ TargetRoot = $ProjectRoot }
if ($ForceExamples) { $applyArgs["ForceExamples"] = $true }
& (Join-Path $ScaffoldRoot "apply-scaffold.ps1") @applyArgs

# ── 2. Catalog (full stack by default) ───────────────────────────
Write-Step "Compose catalog"
$catDst = Join-Path $ProjectRoot "ops\compose\catalog.json"
$catFull = Join-Path $ScaffoldRoot "ops\compose\catalog.full.json"
$catMin = Join-Path $ScaffoldRoot "ops\compose\catalog.minimal.json"
if ($MinimalCatalog) {
    if (-not (Test-Path $catDst)) {
        Copy-Item $catMin $catDst -Force
        Write-Host "  [OK]   ops/compose/catalog.json (minimal)" -ForegroundColor Green
    }
} elseif (Test-Path $catFull) {
    if ($ForceExamples -or -not (Test-Path $catDst)) {
        Copy-Item $catFull $catDst -Force
        Write-Host "  [OK]   ops/compose/catalog.json (full reference stack)" -ForegroundColor Green
    } else {
        Write-Host "  [skip] ops/compose/catalog.json (exists; use -ForceExamples to replace)" -ForegroundColor DarkGray
    }
}

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
    $nginxEx = (Get-ManifestField "adapters.nginx.envExample") -replace '/', '\'
    $nginxTg = (Get-ManifestField "adapters.nginx.env") -replace '/', '\'
    if ($nginxEx -and $nginxTg) {
        Copy-IfMissing -ExampleRel $nginxEx -TargetRel $nginxTg -Optional:$true -Force:$ForceExamples
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
