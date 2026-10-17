# Resolve a working Python on Windows (Store alias) and Unix.

function Get-StackKitPythonArgs {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -c "import sys" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { return , @("py", "-3") }
    }
    foreach ($candidate in @("python3", "python")) {
        if (-not (Get-Command $candidate -ErrorAction SilentlyContinue)) { continue }
        & $candidate -c "import sys" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { return , @($candidate) }
    }
    return $null
}

function Invoke-StackKitPythonExe {
    # Every kit script speaks UTF-8 (PYTHONUTF8): a Python writing to a pipe otherwise encodes in the
    # machine's ANSI code page, and an em dash reaches the reader as a replacement character. Set
    # for the child only -- a launcher run in the operator's session leaves that session as it was.
    param([Parameter(Mandatory = $true)][string[]]$PyArgs, [Parameter(ValueFromRemainingArguments = $true)][string[]]$CommandArgs)
    $prior = $env:PYTHONUTF8
    $env:PYTHONUTF8 = "1"
    try {
        switch ($PyArgs.Count) {
            2 { & $PyArgs[0] $PyArgs[1] @CommandArgs }
            1 { & $PyArgs[0] @CommandArgs }
            default { throw "Invalid Python command args (count=$($PyArgs.Count))" }
        }
    }
    finally {
        $env:PYTHONUTF8 = $prior
    }
}

function Invoke-StackKitPython {
    param(
        [Parameter(Mandatory = $true)][string]$ScriptPath,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$ScriptArgs
    )
    $pyArgs = Get-StackKitPythonArgs
    if (-not $pyArgs) {
        Write-Error "Python not found (tried py -3, python3, python)"
        exit 9009
    }
    Invoke-StackKitPythonExe $pyArgs $ScriptPath @ScriptArgs
    exit $LASTEXITCODE
}
