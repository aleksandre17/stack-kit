"""K1 — the kit names no consumer, and a host still on the old names is told, then carried (ADR-001 decision 1).

Two properties, both read from the one declaration (`lib/identity.json`) and never restated here:

  1. THE BOUNDARY. No tracked file names the legacy kit outside the places that must: the declaration
     itself, the decision records and the changelog (history), and the former command's shims, whose
     PATH is the old name and whose content is not. A consumer's own credential cannot hide in the kit
     under the old prefix, because the old prefix is a legacy name too.
  2. EXPAND–CONTRACT, contracted at 2.0.0 (legacyRemovedIn). A host built on the old names -- derived
     here from the reference consumer by turning every declared rename back -- is no longer read:
     no runtime finds its root, `validate` names each former name, and `migrate --apply`, the one
     reader left, carries it to the current names.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import PKG, WORKING_ROOT
from lib import identity

DECLARATION = json.loads((PKG / "lib" / "identity.json").read_text(encoding="utf-8"))
LEGACY = DECLARATION["legacyKitName"]
LEGACY_PREFIX = DECLARATION["legacyEnvPrefix"]
#: Places that must spell the legacy name: the declaration, history, and nothing else by content.
SPELLS_THE_LEGACY_NAME = ("lib/identity.json", "CHANGELOG.md", "docs/decisions/")
#: The former command's shims are gone with 2.0.0.
LEGACY_PATHS: set[str] = set()


def _tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=PKG, capture_output=True, check=True).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


# ── 1. the boundary ───────────────────────────────────────────────────────────


def test_no_tracked_file_names_the_legacy_kit_outside_the_declaration_and_history():
    named = []
    for rel in _tracked():
        if rel.startswith(SPELLS_THE_LEGACY_NAME):
            continue
        if LEGACY.lower() in rel.lower() and rel not in LEGACY_PATHS:
            named.append(f"{rel}: in its path")
        try:
            text = (PKG / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if LEGACY.lower() in line.lower():
                named.append(f"{rel}:{n}: {line.strip()[:100]}")
    assert not named, "the kit names a consumer:\n  " + "\n  ".join(named)


def test_the_sensor_flags_the_legacy_name_in_any_case():
    # Measured before the tree is: the scan above must see each spelling the rename replaced.
    for specimen in (LEGACY, LEGACY.upper(), LEGACY.capitalize(), f"{LEGACY_PREFIX}_X"):
        assert LEGACY.lower() in specimen.lower()
    assert LEGACY.lower() not in identity.KIT_NAME.lower()


# ── 2. expand–contract ────────────────────────────────────────────────────────


def _legacy_host(tmp_path: Path) -> Path:
    """The reference consumer as a host on the old names: legacy manifest file, legacy field."""
    host = tmp_path / "legacy-host"
    shutil.copytree(WORKING_ROOT, host, ignore=shutil.ignore_patterns("kits"), symlinks=True)
    current = host / identity.MANIFEST_FILENAME
    manifest = json.loads(current.read_text(encoding="utf-8"))
    for old, new in identity.LEGACY_MANIFEST_FIELDS.items():
        *parent, leaf = new.split(".")
        node = manifest
        for part in parent:
            node = node.setdefault(part, {})
        value = node.pop(leaf, "tools/launcher.ps1")
        *oparent, oleaf = old.split(".")
        node = manifest
        for part in oparent:
            node = node.setdefault(part, {})
        node[oleaf] = value
    current.unlink()
    (host / identity.LEGACY_MANIFEST_FILENAMES[0]).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return host


def _legacy_env(host: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith((identity.ENV_PREFIX + "_", LEGACY_PREFIX + "_"))}
    env[f"{LEGACY_PREFIX}_PROJECT_ROOT"] = str(host)
    env[f"{LEGACY_PREFIX}_KIT_ROOT"] = str(PKG)
    env["PYTHONPATH"] = str(PKG)
    return env


def _notices(stderr: str) -> list[str]:
    return [line for line in stderr.splitlines() if "deprecated:" in line]


def _assert_told_once_each(stderr: str, *olds: str) -> None:
    told = _notices(stderr)
    for old in olds:
        lines = [t for t in told if f"deprecated: {old} -> " in t]
        assert len(lines) == 1, f"{old} told {len(lines)} times:\n{stderr}"
        assert identity.LEGACY_REMOVED_IN in lines[0]


FIELD_OLD, FIELD_NEW = next(iter(identity.LEGACY_MANIFEST_FIELDS.items()))

PY_PROBE = f"""
import sys
from lib.identity import adopt_legacy_env
adopt_legacy_env()
from lib.project_context import ProjectContext
from lib.manifest_defaults import read_nested
ctx = ProjectContext.discover()
print(ctx.root)
print(read_nested(ctx.manifest, {FIELD_NEW!r}))
"""


def _bash() -> str | None:
    found = shutil.which("bash")
    # The Windows Subsystem launcher is not the shell the kit's scripts run under.
    if not found or "system32" in found.lower():
        return None
    return found


def _pwsh() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


def test_no_runtime_reads_a_host_on_the_former_names(tmp_path):
    host = _legacy_host(tmp_path)
    ran = subprocess.run([sys.executable, "-B", "-c", PY_PROBE], cwd=host, env=_legacy_env(host),
                         capture_output=True, text=True)
    assert ran.returncode != 0 and "not found" in (ran.stdout + ran.stderr).lower(), ran.stdout + ran.stderr


def test_each_former_name_is_named_for_migrate(tmp_path):
    host = _legacy_host(tmp_path)
    manifest = json.loads((host / identity.LEGACY_MANIFEST_FILENAMES[0]).read_text(encoding="utf-8"))
    found = identity.legacy_names_in(host, manifest, {f"{LEGACY_PREFIX}_PROJECT_ROOT": "x"})
    assert any(identity.LEGACY_MANIFEST_FILENAMES[0] in f for f in found)
    assert any(FIELD_OLD in f for f in found) and any(f"{LEGACY_PREFIX}_PROJECT_ROOT" in f for f in found)


def test_a_former_variable_is_never_read():
    environ = {f"{LEGACY_PREFIX}_PROJECT_ROOT": "old"}
    assert identity.env("PROJECT_ROOT", "none", environ) == "none"
    assert identity.adopt_legacy_env(environ) == [f"{LEGACY_PREFIX}_PROJECT_ROOT"]
    assert environ == {f"{LEGACY_PREFIX}_PROJECT_ROOT": "old"}, "nothing is carried at run time"


# ── 3. the migration a host replays ───────────────────────────────────────────


def _migrate(host: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = _legacy_env(host)
    env[identity.env_name("PROJECT_ROOT")] = str(host)
    return subprocess.run([sys.executable, "-B", str(PKG / "lib" / "migrate_manifest.py"), *args],
                          cwd=host, env=env, capture_output=True, text=True)


def test_migrate_moves_what_the_kit_owns_and_prints_what_the_host_wrote(tmp_path):
    host = _legacy_host(tmp_path)
    former = host / identity.LEGACY_MANIFEST_FILENAMES[0]
    note = host / "NOTES.md"
    words = f"run {LEGACY_PREFIX}_PROJECT_ROOT=. cli/{LEGACY}.sh\n"
    note.write_text(words, encoding="utf-8")

    planned = _migrate(host)
    assert planned.returncode == 0, planned.stderr
    assert former.is_file(), "a dry run moved the manifest"

    ran = _migrate(host, "--apply")
    assert ran.returncode == 0, ran.stderr
    assert not former.exists()
    manifest = json.loads((host / identity.MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert identity._dig(manifest, FIELD_NEW) is not None and identity._dig(manifest, FIELD_OLD) is None
    assert note.read_text(encoding="utf-8") == words, "the host's own words were rewritten"
    assert f"NOTES.md:1: cli/{LEGACY}.sh -> cli/{identity.KIT_NAME}.sh" in ran.stdout


def test_migrate_refuses_two_manifest_homes_and_writes_nothing(tmp_path):
    host = _legacy_host(tmp_path)
    former = host / identity.LEGACY_MANIFEST_FILENAMES[0]
    (host / identity.MANIFEST_FILENAME).write_text(former.read_text(encoding="utf-8"), encoding="utf-8")
    before = former.read_bytes()
    ran = _migrate(host, "--apply")
    assert ran.returncode != 0
    assert former.read_bytes() == before
