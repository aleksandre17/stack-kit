# Copy stack-kit/scaffold → project root (merge; do not overwrite real secrets)
param(
    [string]$TargetRoot = "",
    [switch]$ForceExamples
)

$ErrorActionPreference = "Stop"
$ScaffoldRoot = $PSScriptRoot
if (-not $TargetRoot) {
    $TargetRoot = (Resolve-Path (Join-Path $ScaffoldRoot "..\..\..")).Path
}

$skipNames = @{ "README.md" = $true; "apply-scaffold.ps1" = $true; "apply-scaffold.sh" = $true }
$neverOverwrite = @(
    "ops\config\deploy.env",
    "ops\config\frontend\.env.dev", "ops\config\frontend\.env.prod", "ops\config\frontend\.env.deploy",
    "ops\config\frontend\nginx.env",
    "ops\config\backend\.env.dev", "ops\config\backend\.env.prod", "ops\config\backend\.env.deploy",
    "ops\config\backend\google-credentials.json",
    "ops\config\ssh\id_rsa", "ops\config\ssh\id_ed25519", "ops\config\ssh\config",
    "stack-kit.json"
)

function Should-CopyFile([string]$rel) {
    if ($ForceExamples) { return $true }
    if ($neverOverwrite -contains ($rel -replace "/", "\")) { return -not (Test-Path (Join-Path $TargetRoot $rel)) }
    if ($rel -match '\.example$' -or $rel -match '\\README\.md$' -or $rel -match '/README\.md$') { return $true }
    if ($rel -match '\\.gitkeep$' -or $rel -match '/\.gitkeep$' -or $rel -match '\\.gitignore$') { return $true }
    return -not (Test-Path (Join-Path $TargetRoot $rel))
}

function Copy-ScaffoldTree([string]$srcDir, [string]$relPrefix) {
    Get-ChildItem -LiteralPath $srcDir -Force | ForEach-Object {
        $rel = if ($relPrefix) { "$relPrefix/$($_.Name)" } else { $_.Name }
        $rel = $rel -replace '\\', '/'
        if (-not $relPrefix -and $skipNames.ContainsKey($_.Name)) { return }

        $dest = Join-Path $TargetRoot ($rel -replace '/', '\')
        if ($_.PSIsContainer) {
            if (-not (Test-Path $dest)) { New-Item -ItemType Directory -Path $dest -Force | Out-Null }
            Copy-ScaffoldTree $_.FullName $rel
            return
        }

        if (-not (Should-CopyFile $rel)) {
            Write-Host "  [skip] $rel (exists)" -ForegroundColor DarkGray
            return
        }
        $parent = Split-Path $dest -Parent
        if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
        Copy-Item -LiteralPath $_.FullName -Destination $dest -Force
        Write-Host "  [OK]   $rel" -ForegroundColor Green
    }
}

# catalog.minimal.json → ops/compose/catalog.json if missing
$catSrc = Join-Path $ScaffoldRoot "ops\compose\catalog.minimal.json"
$catDst = Join-Path $TargetRoot "ops\compose\catalog.json"
if ((Test-Path $catSrc) -and -not (Test-Path $catDst)) {
    $dir = Split-Path $catDst -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    Copy-Item $catSrc $catDst -Force
    Write-Host "  [OK]   ops/compose/catalog.json (from catalog.minimal.json)" -ForegroundColor Green
}

Write-Host ""
Write-Host "  stack-kit scaffold → $TargetRoot" -ForegroundColor Cyan
Write-Host ""
Copy-ScaffoldTree $ScaffoldRoot ""
Write-Host ""
Write-Host "  Next:" -ForegroundColor Yellow
Write-Host "    .\tools\stack-kit.ps1 init          # full bootstrap (recommended)"
Write-Host "    — or — copy deploy.env + compose-gen manually"
Write-Host "    See kits\stack-kit\scaffold\README.md"
Write-Host ""
