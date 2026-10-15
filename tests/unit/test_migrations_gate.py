"""K4 — migrations are structure-only; data has one way in (ADR-001 decision 4).

The technology is the driver's declaration: each case reads the declared globs and patterns of a
registered driver and builds a migration in that shape, so no driver's file layout is spelled here.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from lib.migrations_gate import check
from lib.modules import driver_registry

DECLARING = {t: e["migrations"] for t, e in driver_registry().items()
             if isinstance(e, dict) and isinstance(e.get("migrations"), dict)}


def _place(root: Path, module: str, glob: str, name: str, text: str) -> str:
    """A migration file where `glob` would find it, under the module's tree."""
    parts = [p for p in glob.split("/")[:-1] if p != "**"]
    f = root / module / Path(*parts) / name if parts else root / module / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")
    return f.relative_to(root).as_posix()


def _data_line(pattern: str) -> str:
    """A line the driver's own pattern calls data -- found by trying the usual statement shapes."""
    import re

    for line in ('INSERT INTO t VALUES (1);', 'migrationBuilder.InsertData(table: "t");',
                 'migrationBuilder.Sql("INSERT INTO t VALUES (1)");', "update t set a = 1;",
                 "DELETE FROM t;", "COPY t FROM 'f';"):
        if re.search(pattern, line):
            return line
    raise AssertionError(f"no specimen line for {pattern}")


@pytest.mark.parametrize("driver", sorted(DECLARING))
def test_each_declared_data_statement_is_found_and_structure_passes(tmp_path, driver):
    declared = DECLARING[driver]
    manifest = {"modules": {"m": {"type": driver, "path": "m"}}}
    glob = declared["globs"][0]
    ext = glob.rsplit(".", 1)[-1]
    _place(tmp_path, "m", glob, f"V1__shape.{ext}", "CREATE TABLE t (a int);\n")
    assert check(tmp_path, manifest) == []
    for i, pattern in enumerate(declared["data"]):
        rel = _place(tmp_path, "m", glob, f"V{i + 2}__seed.{ext}", "-- seed\n" + _data_line(pattern) + "\n")
        found = check(tmp_path, manifest)
        assert any(f.startswith(f"{rel}:2:") for f in found), (pattern, found)
        (tmp_path / rel).unlink()


@pytest.mark.parametrize("driver", sorted(DECLARING))
def test_allow_data_needs_a_reason(tmp_path, driver):
    declared = DECLARING[driver]
    glob = declared["globs"][0]
    rel = _place(tmp_path, "m", glob, "V2__lookup." + glob.rsplit(".", 1)[-1], _data_line(declared["data"][0]))
    with_reason = {"modules": {"m": {"type": driver, "path": "m", "migrations": {
        "allowData": [{"path": rel, "reason": "the fixed list of absence kinds"}]}}}}
    without = {"modules": {"m": {"type": driver, "path": "m", "migrations": {
        "allowData": [{"path": rel, "reason": ""}]}}}}
    assert check(tmp_path, with_reason) == []
    assert check(tmp_path, without)


def test_excluded_generated_files_are_not_migrations(tmp_path):
    driver, declared = next((t, d) for t, d in DECLARING.items() if d.get("exclude"))
    excluded = declared["exclude"][0].split("/")[-1].replace("*", "Initial")
    _place(tmp_path, "m", declared["globs"][0], excluded, _data_line(declared["data"][0]))
    assert check(tmp_path, {"modules": {"m": {"type": driver, "path": "m"}}}) == []


def test_migrations_beside_the_module_are_found_through_declared_paths(tmp_path):
    driver, declared = next(iter(DECLARING.items()))
    ext = declared["globs"][0].rsplit(".", 1)[-1]
    elsewhere = tmp_path / "core" / "db"
    elsewhere.mkdir(parents=True)
    (elsewhere / f"V1__seed.{ext}").write_text(_data_line(declared["data"][0]), encoding="utf-8")
    manifest = {"modules": {"m": {"type": driver, "path": "m", "migrations": {"paths": ["core/db"]}}}}
    assert check(tmp_path, manifest), "a declared migrations directory was not searched"
