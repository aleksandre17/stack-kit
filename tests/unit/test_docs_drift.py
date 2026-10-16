"""The hand-written docs stay true to the tree (the defect this fixes: REFERENCE.md and
ARCHITECTURE.md went on documenting contracts/, toolkit/layout, toolkit/deploy and stack-deploy
after they were gone). Every kit path a guide names in backticks exists; every
`stack-kit <verb>` it shows is a verb the registry declares, a lifecycle step, or a module alias
form. History (CHANGELOG, the decision records) is exempt: it describes what was."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from conftest import PKG
from lib import identity

KIT_DIRS = ("lib", "toolkit", "cli", "drivers", "config", "compose", "contracts", "scripts", "ci", "adapters", "scaffold")
PATH = re.compile(r"`((?:" + "|".join(KIT_DIRS) + r")/[A-Za-z0-9_./-]+)`")
VERB = re.compile(r"`(?:pwsh \S+ |\./\S+ |)" + re.escape(identity.KIT_NAME) + r" ([a-z][a-z-]*)")
HISTORY = ("CHANGELOG.md", "docs/decisions/", "tests/")


def _tracked() -> set[str]:
    out = subprocess.run(["git", "-C", str(PKG), "ls-files", "-co", "--exclude-standard"], capture_output=True, text=True)
    return {p for p in out.stdout.splitlines() if (PKG / p).exists()}


def _guides() -> list[str]:
    return sorted(p for p in _tracked() if p.endswith(".md") and not p.startswith(HISTORY))


def stale_paths(text: str, tracked: set[str]) -> list[str]:
    dirs = {str(Path(t).parent).replace("\\", "/") for t in tracked}
    dirs |= {"/".join(d.split("/")[:i]) for d in list(dirs) for i in range(1, len(d.split("/")))}
    return sorted({m.group(1).rstrip("/.") for m in PATH.finditer(text)
                   if m.group(1).rstrip("/.") not in tracked and m.group(1).rstrip("/.") not in dirs})


def stale_verbs(text: str, known: set[str]) -> list[str]:
    return sorted({v for v in VERB.findall(text) if v not in known})


def _known_verbs() -> set[str]:
    from lib.cli import registry
    from lib.modules import lifecycle_steps

    return set(registry.discover()) | set(lifecycle_steps()) | {"help"}


def test_every_kit_path_a_guide_names_exists():
    tracked = _tracked()
    found = {g: stale_paths((PKG / g).read_text(encoding="utf-8"), tracked) for g in _guides()}
    found = {g: v for g, v in found.items() if v}
    assert not found, f"a guide names a path that is not there: {found}"


def test_every_verb_a_guide_shows_is_declared():
    known = _known_verbs()
    found = {g: stale_verbs((PKG / g).read_text(encoding="utf-8"), known) for g in _guides()}
    found = {g: v for g, v in found.items() if v}
    assert not found, f"a guide shows a verb the CLI does not have: {found}"


def test_the_sensors_see_a_stale_mention():
    assert stale_paths("see `toolkit/deploy/upload.sh`", {"lib/x.py"}) == ["toolkit/deploy/upload.sh"]
    assert stale_paths("see `lib/x.py` and `lib/`", {"lib/x.py"}) == []
    assert stale_verbs(f"run `{identity.KIT_NAME} stack-deploy`", {"deploy"}) == ["stack-deploy"]
    assert stale_verbs(f"run `{identity.KIT_NAME} deploy api`", {"deploy"}) == []
