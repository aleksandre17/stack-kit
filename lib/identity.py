"""The kit's own identity — declared ONCE, projected everywhere.

Before this module the manifest filename lived in 77 places across three languages.
That is the failure Cardinal III names: a truth with many homes does not become
wrong, it becomes UNVERIFIABLE — every copy stays locally correct while the set
drifts, and no reader can detect the contradiction from where it stands.

So the name is declared here and nowhere else. Renaming the kit is then a change
to THIS FILE, not an archaeology across the tree.

The legacy name is not deleted, it is DECLARED as legacy. A consumer pinned to the
old filename keeps working and is TOLD, once, that it is reading a deprecated name —
an honest, dated transition (Strangler-Fig), never a silent break and never a
permanent second home.
"""
from __future__ import annotations

import os
from pathlib import Path

#: What the kit calls itself. The CLI, the manifest and the env prefix all derive
#: from this one word.
KIT_NAME = "geostat"

#: The manifest a consumer declares its project in.
MANIFEST_FILENAME = f"{KIT_NAME}.ops.json"

#: Names accepted for backward compatibility, most recent first. Reading one of
#: these is legal and warned about; writing one is not done.
LEGACY_MANIFEST_FILENAMES: tuple[str, ...] = ()

#: Environment variables the kit reads are prefixed with this.
ENV_PREFIX = KIT_NAME.upper()


def manifest_filenames() -> tuple[str, ...]:
    """Every filename that may hold a project manifest — canonical first."""
    return (MANIFEST_FILENAME, *LEGACY_MANIFEST_FILENAMES)


def find_manifest(directory: Path) -> Path | None:
    """The manifest in `directory`, preferring the canonical name.

    Returns None when the directory holds no manifest under any accepted name.
    A legacy hit is announced once per path so a consumer learns it is on a
    deprecated name instead of discovering it at the next major version.
    """
    for name in manifest_filenames():
        candidate = directory / name
        if candidate.is_file():
            if name != MANIFEST_FILENAME:
                _warn_legacy(candidate, name)
            return candidate
    return None


def has_manifest(directory: Path) -> bool:
    return find_manifest(directory) is not None


_warned: set[str] = set()


def _warn_legacy(path: Path, name: str) -> None:
    key = str(path)
    if key in _warned or os.environ.get(f"{ENV_PREFIX}_NO_DEPRECATION_NOTICE"):
        return
    _warned.add(key)
    import sys

    print(
        f"[{KIT_NAME}] notice: '{name}' is a deprecated manifest name; "
        f"rename it to '{MANIFEST_FILENAME}'. Both are read for now.",
        file=sys.stderr,
    )
