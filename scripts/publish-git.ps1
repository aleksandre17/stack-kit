# Prepare stack-kit for first push to a new remote (run from package root)
param(
    [string]$RemoteUrl = "",
    [string]$Tag = "",
    [switch]$SkipCommit
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

if (-not (Test-Path ".git")) {
    Write-Host "  git init" -ForegroundColor Cyan
    git init
}

if (-not $SkipCommit) {
    $status = git status --porcelain
    if ($status) {
        Write-Host "  git add + commit" -ForegroundColor Cyan
        git add -A
        $ver = (Get-Content VERSION -Raw).Trim()
        git commit -m "chore: stack-kit v$ver"
    } else {
        Write-Host "  [skip] working tree clean" -ForegroundColor DarkGray
    }
}

git branch -M main 2>$null

if ($RemoteUrl) {
    $existing = git remote get-url origin 2>$null
    if ($LASTEXITCODE -ne 0) {
        git remote add origin $RemoteUrl
        Write-Host "  remote origin = $RemoteUrl" -ForegroundColor Green
    } else {
        Write-Host "  origin already: $existing" -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Host "  git push -u origin main" -ForegroundColor Cyan
    git push -u origin main
}

if ($Tag) {
    git tag -a $Tag -m "stack-kit $Tag" -f 2>$null
    if ($RemoteUrl -or (git remote get-url origin 2>$null)) {
        git push origin $Tag
    }
}

Write-Host ""
Write-Host "  Next: create empty repo on GitHub, then:" -ForegroundColor Yellow
Write-Host "    .\scripts\publish-git.ps1 -RemoteUrl https://github.com/USER/stack-kit.git"
Write-Host "  See README + docs/INSTALL.md for consumers."
Write-Host ""
