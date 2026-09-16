"""Release metadata — version pin for consumers."""
from __future__ import annotations

import re
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]


def test_version_file_semver() -> None:
    ver = (PKG / "VERSION").read_text(encoding="utf-8").strip()
    # SemVer 2.0.0 (official pattern): prerelease/build metadata are valid.
    # No literal pin here — VERSION is the single home of the version; a test
    # restating it is a second home that must be edited on every release.
    assert re.match(
        r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
        r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
        r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
        r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$",
        ver,
    ), ver


def test_changelog_mentions_version() -> None:
    ver = (PKG / "VERSION").read_text(encoding="utf-8").strip()
    changelog = (PKG / "CHANGELOG.md").read_text(encoding="utf-8")
    assert ver in changelog
