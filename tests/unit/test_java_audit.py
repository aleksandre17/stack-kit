"""java-boot declares a dependency audit (ADR-001 amendment 16.2): OSV-Scanner over the module's
Gradle lockfiles, the binary when it is on PATH, else its image through the local engine; a module
that locks nothing is refused, a finding fails the step. No scanner runs here: the command line is
recorded."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from conftest import PKG

SCRIPT = PKG / "drivers" / "java-boot" / "py" / "audit.py"


def _audit():
    spec = importlib.util.spec_from_file_location("java_boot_audit", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _module(tmp_path: Path, *locks: str) -> tuple[Path, dict]:
    for rel in locks:
        (tmp_path / "api" / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "api" / rel).write_text("org.x:y:1.0=runtimeClasspath\n", encoding="utf-8")
    (tmp_path / "api").mkdir(exist_ok=True)
    return tmp_path, {"modules": {"api": {"type": "java-boot", "path": "api"}}}


def test_the_driver_declares_its_audit_and_ci_runs_it():
    from lib.modules import driver_capability, driver_commands

    decl = driver_capability("java-boot", "audit")
    assert decl["scanner"] and decl["image"] and decl["lockfiles"]
    assert ":latest" not in decl["image"] and ":" in decl["image"].rsplit("/", 1)[-1], "a version, never a floating tag"
    assert driver_commands("java-boot")["audit"] == SCRIPT


def test_the_binary_on_path_scans_every_lockfile(tmp_path):
    audit = _audit()
    root, manifest = _module(tmp_path, "gradle.lockfile", "app/gradle.lockfile")
    ran = []
    code = audit.run("api", root, manifest, which=lambda n: f"/bin/{n}", execute=lambda argv: ran.append(argv) or 0)
    assert code == 0
    assert ran == [["/bin/osv-scanner", "scan", "source", "--lockfile", str(root / "api" / "app/gradle.lockfile"),
                    "--lockfile", str(root / "api" / "gradle.lockfile")]]


def test_without_the_binary_the_pinned_image_runs_through_the_local_engine(tmp_path):
    from lib.modules import driver_capability

    audit = _audit()
    root, manifest = _module(tmp_path, "gradle.lockfile")
    ran = []
    audit.run("api", root, manifest, which=lambda n: None, execute=lambda argv: ran.append(argv) or 0)
    image = driver_capability("java-boot", "audit")["image"]
    assert ran == [["docker", "run", "--rm", "-v", f"{root / 'api'}:/src:ro", image, "scan", "source",
                    "--lockfile", "/src/gradle.lockfile"]]
    manifest["modules"]["api"]["audit"] = {"image": "registry.example/osv@sha256:" + "a" * 64}
    ran.clear()
    audit.run("api", root, manifest, which=lambda n: None, execute=lambda argv: ran.append(argv) or 0)
    assert "registry.example/osv@sha256:" + "a" * 64 in ran[0], "a module pins its own digest over the driver's"


def test_a_finding_fails_the_step_and_an_unlocked_module_is_refused(tmp_path, capsys):
    audit = _audit()
    root, manifest = _module(tmp_path, "gradle.lockfile")
    assert audit.run("api", root, manifest, which=lambda n: "/bin/x", execute=lambda argv: audit.FOUND) == 1
    assert "osv-scanner.toml" in capsys.readouterr().err
    (root / "api" / "gradle.lockfile").unlink()
    ran = []
    assert audit.run("api", root, manifest, which=lambda n: "/bin/x", execute=lambda argv: ran.append(argv) or 0) == 1
    assert not ran and "dependency locking" in capsys.readouterr().err


def test_the_command_runs_as_a_driver_command_in_its_own_process(tmp_path):
    """Through the runtime its name selects (config/runtimes.json: *.py), with the module's env."""
    root, _ = _module(tmp_path)
    manifest = {"version": 2, "package": str(PKG), "secrets": "ops/config",
                "modules": {"api": {"type": "java-boot", "role": "api", "path": "api", "secretsModule": "api",
                                    "audit": {"scanner": "no-such-scanner-anywhere", "image": ""}}}}
    from lib import identity

    (root / identity.MANIFEST_FILENAME).write_text(json.dumps(manifest), encoding="utf-8")
    env = {**__import__("os").environ, identity.env_name("PROJECT_ROOT"): str(root), identity.env_name("MODULE_ID"): "api",
           identity.env_name("KIT_ROOT"): str(PKG), "PYTHONPATH": str(PKG)}
    ran = subprocess.run([sys.executable, "-B", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60)
    assert ran.returncode == 1 and "refused: no dependency lockfile" in ran.stderr, ran.stderr
