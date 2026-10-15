"""PowerShell driver scripts must dot-source parent _init.ps1."""
from __future__ import annotations

from pathlib import Path


def test_node_vite_ps1_init_path(pkg_root: Path):
    ps1 = pkg_root / "drivers" / "node-vite" / "ps1"
    assert (ps1.parent / "_init.ps1").is_file()
    wrong = '. "$PSScriptRoot\\_init.ps1"'
    for name in ("check.ps1", "compose.ps1"):
        text = (ps1 / name).read_text(encoding="utf-8")
        assert wrong not in text
        assert "_init.ps1" in text
        assert ".." in text


def test_toolkit_ps1_no_em_dash_in_executable_strings(pkg_root: Path):
    """Unicode em dash inside .Add() breaks Windows PowerShell 5.1 parsing."""
    for path in (pkg_root / "toolkit" / "powershell").glob("*.ps1"):
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "\u2014" in line and ".Add(" in line:
                raise AssertionError(f"{path}:{i} contains em dash in .Add(): {line!r}")
