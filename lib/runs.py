"""The project's runs directory (`identity.runsDir`): local records of what ran -- the run record, the whole
output of a tool whose message was shortened -- never tracked, so it is ignored where it is made."""
from __future__ import annotations

from pathlib import Path

from lib import identity


def runs_dir(root: Path) -> Path:
    d = root / identity.RUNS_DIR
    d.mkdir(parents=True, exist_ok=True)
    ignore = root / identity.RUNS_DIR.split("/")[0] / ".gitignore"
    if not ignore.is_file():
        ignore.write_text("*\n", encoding="utf-8")
    return d
