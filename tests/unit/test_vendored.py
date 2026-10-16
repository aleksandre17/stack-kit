"""A file another kit owns is held byte for byte (ADR-001 amendment 16.4): its sha256 is the one
recorded with its origin, and -- where the origin's checkout sits beside this kit -- the origin's
file still has it, so a change there is seen here and taken, never edited in place."""
from __future__ import annotations

import hashlib
import json
import re

import pytest

from conftest import PKG

VENDORED = json.loads((PKG / "config" / "vendored.json").read_text(encoding="utf-8"))


def _sha(path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


@pytest.mark.parametrize("rel", sorted(VENDORED["files"]))
def test_a_vendored_file_is_its_recorded_bytes(rel):
    rec = VENDORED["files"][rel]
    assert re.fullmatch(r"[0-9a-f]{40}", rec["commit"]) and rec["origin"].startswith("https://")
    assert _sha(PKG / rel) == rec["sha256"], f"{rel} was edited here: take it again from {rec['origin']} {rec['path']}"


@pytest.mark.parametrize("rel", sorted(VENDORED["files"]))
def test_a_vendored_file_matches_its_origin_where_the_origin_is_beside_the_kit(rel):
    rec = VENDORED["files"][rel]
    origin = (PKG / rec["sibling"] / rec["path"]).resolve()
    if not origin.is_file():
        pytest.skip(f"{rec['origin']} is not checked out beside the kit")
    assert _sha(origin) == rec["sha256"], f"the origin changed: take {rec['path']} again and record its sha256"


def test_the_extension_point_registry_validates_against_the_shared_schema():
    from lib import schema_check

    reg = json.loads((PKG / "config" / "extension-points.json").read_text(encoding="utf-8"))
    schema = json.loads((PKG / "config" / "extension-points.schema.json").read_text(encoding="utf-8"))
    assert schema.get("$id") == "extension-points", "the shared schema, not a kit-local one"
    assert schema_check.validate(reg, schema) == []


def test_the_shared_schema_sees_a_point_outside_its_shape():
    from lib import schema_check

    schema = json.loads((PKG / "config" / "extension-points.schema.json").read_text(encoding="utf-8"))
    bad = {"schema_version": 1, "points": [{"id": "x", "purpose": "p", "host_path": "h", "template": None, "schema": None,
                                            "cardinality": "one", "required_by": ["init"], "merges_into": "instance",
                                            "companions": "y"}]}
    assert schema_check.validate(bad, schema)
