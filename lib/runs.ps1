# The run record: one JSON line per delivery rung and lifecycle step that ran, appended to the host's
# runs directory (lib/identity.json `runsDir`), so lead time, deployment frequency, change failure
# rate and time to restore can be computed from what actually ran (ADR-001 amendment 8).
# The directory ignores itself (a `.gitignore` of `*`): the record is this machine's observation,
# never a tracked file, and no host .gitignore has to know it. A record that cannot be written is
# said and never fails the step it records.

function Get-StackKitRunsFile {
    $root = Get-ProjectRootFromManifest
    if (-not $root) { return $null }
    $rel = (Get-KitIdentity).runsDir
    $dir = Join-Path $root ($rel -replace '/', [System.IO.Path]::DirectorySeparatorChar)
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $top = Join-Path $root (($rel -split '/')[0])
    $ignore = Join-Path $top ".gitignore"
    if (-not (Test-Path $ignore)) {
        [System.IO.File]::WriteAllText($ignore, "*`n", [System.Text.UTF8Encoding]::new($false))
    }
    return (Join-Path $dir "runs.jsonl")
}

function Get-StackKitGitState {
    $root = Get-ProjectRootFromManifest
    $sha = (& git -C $root rev-parse HEAD 2>$null)
    $dirty = $null
    if ($sha) { $dirty = [bool](& git -C $root status --porcelain --untracked-files=no 2>$null) }
    return @{ sha = $(if ($sha) { [string]$sha } else { $null }); dirty = $dirty }
}

function Invoke-RecordedStep {
    # Runs $Action (a scriptblock whose last act sets $LASTEXITCODE) and records it; returns the exit code.
    param(
        [Parameter(Mandatory = $true)][string]$Kind,
        [Parameter(Mandatory = $true)][string]$Step,
        [Parameter(Mandatory = $true)][string]$ModuleId,
        [string]$Environment = "",
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )
    $git = Get-StackKitGitState
    $started = [DateTimeOffset]::UtcNow
    $global:LASTEXITCODE = 0
    $code = 1
    try {
        & $Action | Out-Host
        $code = if ($null -ne $LASTEXITCODE) { [int]$LASTEXITCODE } else { 0 }
    } catch {
        Write-Host "[$ModuleId $Step] $($_.Exception.Message)" -ForegroundColor Red
        $code = 1
    }
    $ended = [DateTimeOffset]::UtcNow
    $record = [ordered]@{
        schema      = 1
        kind        = $Kind
        step        = $Step
        module      = $ModuleId
        environment = $(if ($Environment) { $Environment } else { $null })
        startedAt   = $started.ToString("o")
        endedAt     = $ended.ToString("o")
        durationMs  = [int]($ended - $started).TotalMilliseconds
        exit        = $code
        gitSha      = $git.sha
        gitDirty    = $git.dirty
    }
    try {
        $file = Get-StackKitRunsFile
        if ($file) {
            $line = ($record | ConvertTo-Json -Compress) + "`n"
            [System.IO.File]::AppendAllText($file, $line, [System.Text.UTF8Encoding]::new($false))
        }
    } catch {
        Write-Host "  [run record] not written: $($_.Exception.Message)" -ForegroundColor Yellow
    }
    return $code
}
