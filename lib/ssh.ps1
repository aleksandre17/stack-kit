# SSH helpers for stack-kit deploy — optional ops/config/ssh/ keys

function Resolve-StackKitRepoPath {
    param([string]$Path)
    if (-not $Path) { return $null }
    if ([System.IO.Path]::IsPathRooted($Path)) { return $Path }
    Join-Path (Get-MonorepoRoot) ($Path -replace '/', '\')
}

function Get-StackKitSshExtraArgs {
    # The openssh arguments of the selected deploy target (resolve_cli.py ssh-args): port, strict host
    # keys against its pinned file, its identity reference, its options -- or, without a declared
    # target, the deprecated DEPLOY_SSH_* of deploy.env. The resolver decides; this only asks
    # (ADR-001 amendment 9). rsync's transport is the same ssh (RSYNC_RSH).
    $sshArgs = [System.Collections.ArrayList]@()
    foreach ($a in @(Invoke-KitResolver -Arguments @('ssh-args'))) { if ($a) { [void]$sshArgs.Add([string]$a) } }
    if ($sshArgs.Count -gt 0) {
        $env:RSYNC_RSH = "ssh " + (($sshArgs | ForEach-Object { if ($_ -match '\s') { "'$_'" } else { $_ } }) -join ' ')
    }
    return $sshArgs
}

function Invoke-StackKitRemoteBash {
    param([string]$Script)
    $server = Get-DeployEnvValue "DEPLOY_SERVER"
    if (-not $server) { throw "no deploy server: declare a target (deploy.targets) -- deploy.env DEPLOY_SERVER is deprecated" }
    $sshExtra = @(Get-StackKitSshExtraArgs)
    $payload = (($Script -replace "`r", "") -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ }) -join "`n"
    if (-not $payload.EndsWith("`n")) { $payload += "`n" }

    # Windows PowerShell mangles bash -lc "..." quoting; pipe LF-only script via stdin.
    $tmp = [System.IO.Path]::GetTempFileName()
    try {
        $utf8NoBom = New-Object System.Text.UTF8Encoding $false
        [System.IO.File]::WriteAllText($tmp, $payload, $utf8NoBom)
        $sshCmd = Get-Command ssh -ErrorAction Stop
        $argList = New-Object System.Collections.Generic.List[string]
        foreach ($a in $sshExtra) { [void]$argList.Add($a) }
        [void]$argList.Add($server)
        [void]$argList.Add("bash")
        [void]$argList.Add("-s")
        $proc = Start-Process -FilePath $sshCmd.Source -ArgumentList $argList.ToArray() `
            -RedirectStandardInput $tmp -Wait -PassThru -NoNewWindow
        return $proc.ExitCode
    }
    finally {
        if (Test-Path $tmp) { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
    }
}

function Invoke-StackKitRemotePreflight {
    # Claims the project's directory on the target (ownership marker) or refuses one another project
    # owns, and refuses a declared host port another compose project publishes -- before any write.
    param([string[]]$Services = @())
    $script = (@(Invoke-KitResolver -Arguments (@('remote-preflight') + $Services)) -join "`n")
    if (-not $script.Trim()) { return }
    $code = Invoke-StackKitRemoteBash -Script $script
    if ($code -ne 0) { throw "remote preflight refused the deploy (exit $code): see the message above" }
}

function Assert-StackKitConfined {
    # A remote path a remove may touch lies inside this project's directory on the target.
    param([Parameter(Mandatory = $true)][string]$Path)
    $ok = Invoke-KitResolver -Arguments @('confined', $Path) | Select-Object -First 1
    if (-not $ok) { throw "REFUSED: $Path is outside this project's directory on the target" }
}

function Invoke-StackKitScp {
    param([string]$LocalPath, [string]$RemoteDest)
    $server = Get-DeployEnvValue "DEPLOY_SERVER"
    if (-not $server) { throw "DEPLOY_SERVER not set" }
    $sshExtra = @(Get-StackKitSshExtraArgs)
    & scp @sshExtra $LocalPath "${server}:${RemoteDest}" 2>&1 | ForEach-Object {
        Write-Host "[scp] $_" -ForegroundColor DarkGray
    }
    return $LASTEXITCODE
}
