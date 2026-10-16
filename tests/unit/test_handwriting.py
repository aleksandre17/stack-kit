"""K3 — the agent kit's handwriting: decisions, four guides each of a declared kind (ADR-001 decision 3).

Fifteen guides once restated one another; a sixteenth would be how that starts again. So `docs/`
holds the decision records and exactly the four guides the decision names, each declaring what it
owns, and every relative link in a guide reaches a file.
"""
from __future__ import annotations

import re

from conftest import PKG
from lib.identity import KIT_NAME, LEGACY_KIT_NAME

GUIDES = {"INSTALL.md": "install", "ADOPT.md": "adoption", "REFERENCE.md": "reference",
          "GOLDEN-PATHS.md": "golden-paths"}
DOCS = PKG / "docs"


def _front_matter(text: str) -> dict[str, str]:
    m = re.match(r"^﻿?---\n(.*?)\n---\n", text.replace("\r\n", "\n"), re.S)
    if not m:
        return {}
    return dict(line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)


def test_docs_holds_the_decisions_and_exactly_the_four_guides():
    present = {p.name for p in DOCS.iterdir() if p.is_file()}
    assert present == set(GUIDES), f"docs/ holds {sorted(present)}"
    assert (DOCS / "decisions").is_dir()


def test_each_guide_declares_its_kind_and_what_it_owns():
    for name, owns in GUIDES.items():
        meta = {k.strip(): v.strip() for k, v in _front_matter((DOCS / name).read_text(encoding="utf-8")).items()}
        assert meta.get("kind") == "guide", name
        assert meta.get("owns") == owns, name


def test_every_relative_link_in_a_guide_reaches_a_file():
    broken = []
    # Every page the kit ships to be read in place (scaffold pages are read in the host they land in,
    # and the changelog is a record of what pages were then).
    pages = [*(DOCS / name for name in GUIDES), PKG / "README.md", PKG / "ARCHITECTURE.md",
             *(p for d in ("drivers", "toolkit", "ci", "adapters", "compose", "contracts", "lib")
               for p in (PKG / d).rglob("*.md"))]
    for page in (p.resolve() for p in pages):
        for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", page.read_text(encoding="utf-8")):
            if re.match(r"^[a-z]+:", target):
                continue
            if not (page.parent / target).exists():
                broken.append(f"{page.relative_to(PKG).as_posix()} -> {target}")
    assert not broken, "\n".join(broken)


#: The launchers the kit ships: its CLI, its former name, and the two a host is scaffolded with.
LAUNCHERS = [f"cli/{KIT_NAME}.ps1", f"cli/{LEGACY_KIT_NAME}.ps1", f"scaffold/tools/{KIT_NAME}.ps1",
             f"scaffold/ops/cli/{KIT_NAME}.ps1"]


def test_no_launcher_declares_an_advanced_param_block():
    # Found while reducing the guides: with any [Parameter()] in the block, PowerShell adds its common
    # parameters, and `stack-kit stack up -d` lost `-d` to -Debug before the CLI ever saw it.
    advanced = []
    for rel in LAUNCHERS:
        text = (PKG / rel).read_text(encoding="utf-8")
        block = re.search(r"^param\((.*?)\)\s*$", text, re.M | re.S)
        assert block, f"{rel} declares no param block"
        if "[Parameter" in block.group(1) or "[CmdletBinding" in text:
            advanced.append(rel)
    assert not advanced, f"advanced param blocks swallow operands like -d: {advanced}"
