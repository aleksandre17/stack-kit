"""Every PowerShell script the kit ships parses. A script that does not is a command no host can run, and
nothing else would say so until someone ran it (one did: `infra` shipped unparseable for a release)."""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from conftest import PKG

PWSH = shutil.which("pwsh") or shutil.which("powershell")
#: One process parses them all, and says how many it parsed -- a sweep that read nothing must not pass --
#: with each file's errors as `path: line: message`.
PARSE = r"""
param([string]$Listed)
$parsed = 0
$found = @()
foreach ($f in (Get-Content -Raw -LiteralPath $Listed | ConvertFrom-Json)) {
  $errors = $null
  [void][System.Management.Automation.Language.Parser]::ParseFile($f, [ref]$null, [ref]$errors)
  $parsed++
  foreach ($e in $errors) { $found += "${f}: $($e.Extent.StartLineNumber): $($e.Message)" }
}
@{ parsed = $parsed; errors = @($found) } | ConvertTo-Json -Compress
"""


@pytest.mark.skipif(PWSH is None, reason="needs PowerShell")
def test_every_shipped_powershell_script_parses(tmp_path):
    scripts = sorted(str(p) for p in PKG.rglob("*.ps1") if not {"tests", ".git", "node_modules"} & set(p.relative_to(PKG).parts))
    assert scripts, "no PowerShell script found -- the sweep itself is broken"
    listed, parser = tmp_path / "scripts.json", tmp_path / "parse.ps1"
    listed.write_text(json.dumps(scripts), encoding="utf-8")
    parser.write_text(PARSE, encoding="utf-8")
    ran = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File", str(parser), "-Listed", str(listed)],
                         capture_output=True, text=True)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    said = json.loads(ran.stdout)
    assert said["parsed"] == len(scripts), said
    assert said["errors"] == [], said["errors"]
