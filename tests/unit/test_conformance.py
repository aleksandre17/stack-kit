"""The standards conformance map is machine-checked: shaped by its schema, and every `conformant` row
names evidence that exists -- a test this suite collects (so it runs it), or a verb the CLI declares;
every row that is not conformant says why."""
from __future__ import annotations

import ast
import json

from conftest import PKG
from lib import schema_check

MAP = json.loads((PKG / "config" / "conformance.json").read_text(encoding="utf-8"))


def _test_exists(node: str) -> bool:
    path, _, name = node.partition("::")
    f = PKG / path
    if not f.is_file():
        return False
    tree = ast.parse(f.read_text(encoding="utf-8"))
    funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    fn = funcs.get(name)
    return fn is not None and not any("skip" in ast.unparse(d) and "skipif" not in ast.unparse(d) for d in fn.decorator_list)


def test_the_map_has_its_shape():
    schema = json.loads((PKG / "config" / "conformance.schema.json").read_text(encoding="utf-8"))
    assert schema_check.validate(MAP, schema) == []


def test_a_conformant_row_names_evidence_that_exists_and_runs():
    from lib.cli import registry

    verbs = set(registry.discover())
    bad = []
    for row in MAP["rows"]:
        if row["status"] != "conformant":
            continue
        if not row["evidence"]:
            bad.append(f"{row['standard']} {row['clause']}: conformant without evidence")
        for ev in row["evidence"]:
            if not (_test_exists(ev) if "::" in ev else ev in verbs):
                bad.append(f"{row['standard']} {row['clause']}: evidence {ev} does not exist")
    assert not bad, "\n".join(bad)


def test_every_other_row_says_why():
    assert not [r for r in MAP["rows"] if r["status"] != "conformant" and not r.get("why")]


def test_the_sensor_refuses_missing_evidence():
    assert not _test_exists("tests/unit/test_conformance.py::no_such_test")
    assert _test_exists("tests/unit/test_conformance.py::test_the_map_has_its_shape")
