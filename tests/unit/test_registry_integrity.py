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


def test_a_hybrid_rung_has_a_declared_launch_step(pkg_root: Path):
    # The host run is the driver's declared script, never a branch in the runner (ADR-001 K6).
    reg = json.loads((pkg_root / "drivers" / "registry.json").read_text(encoding="utf-8"))
    for driver_id, entry in reg.items():
        via_hybrid = any(r.get("via") == "hybrid" for r in entry.get("delivery", {}).values())
        script = (entry.get("hybrid") or {}).get("script")
        assert script or not via_hybrid, f"{driver_id} delivers through hybrid but declares no hybrid.script"
        if script:
            assert (pkg_root / "drivers" / driver_id / script).is_file(), f"{driver_id}.hybrid -> missing {script}"
