"""Build output is never tracked (ADR-001 amendment 16.12): each driver declares what its toolchain
writes (`outputs`), a host adds its own (`modules.<id>.outputs`, never a removal), and validate
refuses every tracked file an output matches -- counted per output, with the fix. Proven on a
fixture driver the kit does not ship, so the rule is the declaration's, not a driver's."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from lib import tracked_outputs
from lib.modules import driver_registry

#: A driver no kit ships: what its toolchain writes is all the check knows of it.
REGISTRY = {"fx-build": {"label": "a fixture toolchain", "roles": ["api"], "commands": {}, "outputs": ["bin/", "obj/"]},
            "fx-plain": {"label": "declares no outputs", "roles": ["api"], "commands": {}}}


def _repo(tmp_path: Path, files: dict[str, str], *, track: list[str]) -> Path:
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    if track:
        subprocess.run(["git", "-C", str(tmp_path), "add", "--", *track], check=True)
    return tmp_path


def _manifest(**modules: dict) -> dict:
    return {"modules": {mid: {"type": "fx-build", "path": f"apps/{mid}", **cfg} for mid, cfg in modules.items()}}


def test_a_tracked_output_is_refused_counted_with_its_fix(tmp_path):
    root = _repo(tmp_path, {"apps/svc/Program.src": "x", "apps/svc/bin/x.dll": "b", "apps/svc/sub/bin/Debug/y.dll": "b",
                            "apps/svc/sub/bin/Debug/z.pdb": "b"},
                 track=["apps/svc/Program.src", "apps/svc/bin/x.dll", "apps/svc/sub/bin"])
    found = tracked_outputs.problems(root, _manifest(svc={}), REGISTRY)
    assert found == [
        "modules.svc: 1 tracked file in build output apps/svc/bin/ ('bin/', driver fx-build) -- "
        "untrack: git rm -r --cached apps/svc/bin; ignore: add 'apps/svc/**/bin/' to .gitignore",
        "modules.svc: 2 tracked files in build output apps/svc/sub/bin/ ('bin/', driver fx-build) -- "
        "untrack: git rm -r --cached apps/svc/sub/bin; ignore: add 'apps/svc/**/bin/' to .gitignore"]


def test_an_untracked_output_on_disk_is_fine(tmp_path):
    root = _repo(tmp_path, {"apps/svc/Program.src": "x", "apps/svc/bin/x.dll": "b", "apps/svc/obj/a.json": "o"},
                 track=["apps/svc/Program.src"])
    assert tracked_outputs.problems(root, _manifest(svc={}), REGISTRY) == []


def test_outside_a_repository_nothing_is_tracked_so_nothing_is_refused(tmp_path):
    (tmp_path / "apps" / "svc" / "bin").mkdir(parents=True)
    (tmp_path / "apps" / "svc" / "bin" / "x.dll").write_text("b", encoding="utf-8")
    assert tracked_outputs.tracked(tmp_path) is None
    assert tracked_outputs.problems(tmp_path, _manifest(svc={}), REGISTRY) == []


def test_a_host_added_output_is_honoured_and_extends_the_drivers(tmp_path):
    root = _repo(tmp_path, {"apps/svc/reports/r.html": "r", "apps/svc/schema.gen.json": "{}", "apps/svc/bin/x.dll": "b",
                            "apps/plain/bin/kept.txt": "a source file a driver with no outputs owns"},
                 track=["apps"])
    manifest = _manifest(svc={"outputs": ["reports/", "*.gen.json", "!bin/"]}, plain={"type": "fx-plain"})
    found = tracked_outputs.problems(root, manifest, REGISTRY)
    assert [f.split(" -- ")[0] for f in found] == [
        "modules.svc: 1 tracked file in build output apps/svc/bin/ ('bin/', driver fx-build)",
        "modules.svc: 1 tracked file in build output apps/svc/reports/ ('reports/', modules.svc.outputs)",
        "modules.svc: 1 tracked file in build output apps/svc/schema.gen.json ('*.gen.json', modules.svc.outputs)"]
    assert tracked_outputs.module_outputs(manifest["modules"]["svc"], REGISTRY) == ["bin/", "obj/", "reports/", "*.gen.json"]


def test_a_file_of_a_nested_module_is_judged_by_that_module_alone(tmp_path):
    root = _repo(tmp_path, {"apps/outer/bin/x.dll": "b", "apps/outer/inner/bin/tool.sh": "source of the inner module"},
                 track=["apps"])
    manifest = {"modules": {"outer": {"type": "fx-build", "path": "apps/outer"},
                            "inner": {"type": "fx-plain", "path": "apps/outer/inner"}}}
    assert [f.split(":")[0] for f in tracked_outputs.problems(root, manifest, REGISTRY)] == ["modules.outer"]
    assert "apps/outer/bin/" in tracked_outputs.problems(root, manifest, REGISTRY)[0]


def test_a_module_at_the_root_names_root_paths(tmp_path):
    root = _repo(tmp_path, {"obj/a.json": "o"}, track=["obj"])
    found = tracked_outputs.problems(root, {"modules": {"app": {"type": "fx-build", "path": "."}}}, REGISTRY)
    assert found == ["modules.app: 1 tracked file in build output obj/ ('obj/', driver fx-build) -- "
                     "untrack: git rm -r --cached obj; ignore: add '**/obj/' to .gitignore"]


@pytest.mark.parametrize("driver", sorted(driver_registry()))
def test_every_kit_driver_declares_what_its_toolchain_writes(driver):
    assert driver_registry()[driver].get("outputs"), f"{driver}: declares no outputs"


def test_a_removal_is_refused_by_the_schema():
    from conftest import PKG
    from lib.schema_check import validate

    schema = json.loads((PKG / "manifest.schema.json").read_text(encoding="utf-8"))
    module = schema["properties"]["modules"]["additionalProperties"]["properties"]["outputs"]
    assert validate(["dist/"], module) == []
    assert validate(["!bin/"], module)


def test_validate_refuses_a_tracked_output(tmp_path, monkeypatch):
    from test_validate_manifest import _golden_tree
    from lib.validate_manifest import validate_manifest

    monkeypatch.delenv("STACK_KIT_PROJECT_ROOT", raising=False)
    root = _golden_tree(tmp_path)
    (root / "apps" / "api" / "build" / "libs").mkdir(parents=True, exist_ok=True)
    (root / "apps" / "api" / "build" / "libs" / "app.jar").write_bytes(b"PK")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    errs, _ = validate_manifest(root)
    assert not [e for e in errs if e.startswith("outputs:")], errs
    subprocess.run(["git", "-C", str(root), "add", "--", "apps/api/build/libs/app.jar"], check=True)
    errs, _ = validate_manifest(root)
    assert [e for e in errs if e.startswith("outputs:")] == [
        "outputs: modules.api: 1 tracked file in build output apps/api/build/ ('build/', driver java-boot) -- "
        "untrack: git rm -r --cached apps/api/build; ignore: add 'apps/api/**/build/' to .gitignore"]
