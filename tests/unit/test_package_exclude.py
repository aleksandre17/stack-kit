"""A module keeps files out of every archive -- and so every image -- of it (ADR-001 amendment 16.9):
`package.exclude`, applied by the one package step every driver goes through, whatever its artifacts'
root (the module, or the staged `{out}`); the release's provenance records the patterns and the files
they kept out. Fixture files only."""
from __future__ import annotations

import json

from delivery_host import commit, host, manifest_of
from lib import identity, package


def _exclude(root, patterns, **registry_edit):
    m = manifest_of(root)
    m["modules"]["edge"]["package"] = {"exclude": patterns}
    (root / identity.MANIFEST_FILENAME).write_text(json.dumps(m), encoding="utf-8")
    if registry_edit:
        reg_file = root / "drivers" / "registry.json"
        reg = json.loads(reg_file.read_text(encoding="utf-8"))
        for path, value in registry_edit.items():
            cur = reg["fixture-svc"]
            *head, last = path.split("__")
            for part in head:
                cur = cur[part]
            cur[last] = value
        reg_file.write_text(json.dumps(reg), encoding="utf-8")
    commit(root, "with exclusions")


def test_excluded_files_never_reach_the_archive_and_the_provenance_says_which(tmp_path, monkeypatch):
    root = host(tmp_path)
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    out = root / "apps" / "edge" / "out"
    out.mkdir(parents=True)
    (out / "app.bin").write_text("v1\n", encoding="utf-8")
    for name in ("appsettings.json", "appsettings.Development.json", "appsettings.Production.json"):
        (out / name).write_text("{}", encoding="utf-8")
    _exclude(root, ["appsettings.Development.json", "out/appsettings.Production.json"])
    meta, trees = package.read(package.pack(root, manifest_of(root), "edge"))
    names = set(trees["edge"])
    assert "out/appsettings.json" in names and "out/app.bin" in names
    assert not {"out/appsettings.Development.json", "out/appsettings.Production.json"} & names
    assert meta["excluded"] == {"patterns": ["appsettings.Development.json", "out/appsettings.Production.json"],
                                "files": ["out/appsettings.Development.json", "out/appsettings.Production.json"]}


def test_a_staged_output_is_held_to_the_same_exclusions(tmp_path, monkeypatch):
    root = host(tmp_path)
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    _exclude(root, ["appsettings.*.json"], package__artifacts=["{out}"], container__artifact="*.bin")
    staged = package.staging(root, "edge")
    staged.mkdir(parents=True)
    (staged / "app.bin").write_text("v1\n", encoding="utf-8")
    (staged / "appsettings.json").write_text("{}", encoding="utf-8")
    (staged / "appsettings.Production.json").write_text("{}", encoding="utf-8")
    meta, trees = package.read(package.pack(root, manifest_of(root), "edge"))
    assert "appsettings.json" in trees["edge"] and "appsettings.Production.json" not in trees["edge"]
    assert meta["excluded"]["files"] == ["appsettings.Production.json"]


def test_a_module_that_excludes_nothing_packages_as_before(tmp_path, monkeypatch):
    root = host(tmp_path)
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    (root / "apps" / "edge" / "out").mkdir(parents=True)
    (root / "apps" / "edge" / "out" / "app.bin").write_text("v1\n", encoding="utf-8")
    meta, _trees = package.read(package.pack(root, manifest_of(root), "edge"))
    assert "excluded" not in meta
