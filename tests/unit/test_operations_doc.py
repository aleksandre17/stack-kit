"""The operator documentation is derived from the verb registry, never written by hand: the
committed docs/OPERATIONS.md is exactly what `help --markdown` renders (regenerate it after a verb
changes), and every verb in it is one the registry declares."""
from __future__ import annotations

import re

from conftest import PKG
from lib import identity
from lib.cli import registry


def test_the_operations_doc_is_what_the_registry_renders():
    want = registry.markdown(registry.discover(), identity.KIT_NAME)
    have = (PKG / "docs" / "OPERATIONS.md").read_text(encoding="utf-8")
    assert have == want, f"docs/OPERATIONS.md drifted from the registry: regenerate with `{identity.KIT_NAME} help --markdown`"


def test_every_documented_verb_is_declared():
    verbs = set(registry.discover())
    documented = set(re.findall(r"^### `([^`]+)`", (PKG / "docs" / "OPERATIONS.md").read_text(encoding="utf-8"), re.M))
    assert documented == {v for v in verbs if v != "<step>"} | ({"<step>"} & documented)
