"""Every registry command must point to an existing script."""
from __future__ import annotations

import json
from pathlib import Path


def test_all_driver_commands_exist(pkg_root: Path):
    reg_path = pkg_root / "drivers" / "registry.json"
    reg = json.loads(reg_path.read_text(encoding="utf-8"))
    for driver_id, entry in reg.items():
        runtime = entry.get("runtime", "bash")
        for cmd, rel in entry.get("commands", {}).items():
            path = pkg_root / "drivers" / driver_id / Path(rel)
            assert path.is_file(), f"{driver_id}.{cmd} -> missing {path}"
