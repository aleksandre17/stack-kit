"""The launcher finds Python as an argv, never a bare string: PowerShell unrolls a one-element array
on `return`, and a caller's `[0]` then took the first letter of `python3` -- every `mod` step on a
Linux runner failed with "The term 'p' is not recognized"."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "lib" / "stack-kit-python.ps1"


def _resolve(present: str) -> list[str]:
    pwsh = shutil.which("pwsh")
    if not pwsh:
        pytest.skip("no pwsh on this machine")
    # Only `present` answers, as a function standing in for the interpreter: no `py` launcher, as on Linux.
    body = (f"function {present} {{ $global:LASTEXITCODE = 0 }}; "
            "function Get-Command { param([string]$Name, $ErrorAction) "
            f"if ($Name -eq '{present}') {{ Microsoft.PowerShell.Core\\Get-Command {present} }} }}; "
            f". '{SCRIPT.as_posix()}'; "
            "$py = Get-StackKitPythonArgs; "
            "'ARRAY=' + ($py -is [array]); 'FIRST=' + $py[0]")
    done = subprocess.run([pwsh, "-NoProfile", "-Command", body], capture_output=True, text=True)
    return done.stdout.split()


@pytest.mark.parametrize("present", ["python3", "python"])
def test_a_lone_interpreter_comes_back_as_an_argv_of_one(present):
    assert _resolve(present) == ["ARRAY=True", f"FIRST={present}"]
