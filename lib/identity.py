"""The kit's own identity — declared ONCE, projected everywhere.

Before this module the manifest filename lived in 77 places across three languages.
That is the failure Cardinal III names: a truth with many homes does not become
wrong, it becomes UNVERIFIABLE — every copy stays locally correct while the set
drifts, and no reader can detect the contradiction from where it stands.

So the name is declared here and nowhere else. Renaming the kit is then a change
to THIS FILE, not an archaeology across the tree.

A legacy name is not deleted, it is DECLARED as legacy (ADR-001 decision 1). A
consumer still on an old manifest name, environment prefix or manifest field keeps
working and is TOLD, once per name, what replaces it — an honest, dated transition
(expand–contract), never a silent break and never a permanent second home.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, MutableMapping

#: The ONE declaration, shared byte-for-byte with bash and PowerShell. Python does
#: not own the kit's name; it PROJECTS it, exactly as the other two runtimes do.
_DECLARATION = json.loads(
    (Path(__file__).resolve().parent / "identity.json").read_text(encoding="utf-8")
)

#: What the kit calls itself.
KIT_NAME: str = _DECLARATION["kitName"]

#: The manifest a consumer declares its project in.
MANIFEST_FILENAME: str = _DECLARATION["manifestFilename"]

#: Names accepted for backward compatibility, most recent first. Reading one of
#: these is legal and warned about; writing one is not done.
LEGACY_MANIFEST_FILENAMES: tuple[str, ...] = tuple(
    _DECLARATION.get("legacyManifestFilenames") or ()
)

#: Environment variables the kit reads are prefixed with this.
ENV_PREFIX: str = _DECLARATION["envPrefix"]

#: The prefix the kit's variables carried before; read with a notice until LEGACY_REMOVED_IN.
LEGACY_ENV_PREFIX: str = _DECLARATION.get("legacyEnvPrefix") or ""

#: The marker a deploy leaves on the server, and the one older deploys left there.
DEPLOY_MARKER: str = _DECLARATION["deployMarker"]
LEGACY_DEPLOY_MARKER: str = _DECLARATION.get("legacyDeployMarker") or ""

#: Where a consumer vendors the kit (pre-v2 root discovery looks for these).
VENDOR_DIRS: tuple[str, ...] = tuple(_DECLARATION.get("vendorDirs") or ())
LEGACY_VENDOR_DIRS: tuple[str, ...] = tuple(_DECLARATION.get("legacyVendorDirs") or ())

#: Where a host keeps the record of what ran (lib/runs.ps1): this machine's, ignored by itself.
RUNS_DIR: str = _DECLARATION["runsDir"]

#: Manifest fields renamed in place: {old dotted path: new dotted path}.
LEGACY_MANIFEST_FIELDS: dict[str, str] = dict(_DECLARATION.get("legacyManifestFields") or {})

#: The name the kit carried before, and so its former command's name.
LEGACY_KIT_NAME: str = _DECLARATION.get("legacyKitName") or ""

#: The release that stops reading every legacy name above.
LEGACY_REMOVED_IN: str = _DECLARATION.get("legacyRemovedIn") or ""


def manifest_filenames() -> tuple[str, ...]:
    """The filename a project manifest is read from. Since 2.0.0 (LEGACY_REMOVED_IN) only the
    canonical one: a former name is refused by `validate` and carried by `migrate --apply`."""
    return (MANIFEST_FILENAME,)


def find_manifest(directory: Path) -> Path | None:
    """The manifest in `directory`, preferring the canonical name.

    Returns None when the directory holds no manifest under any accepted name.
    """
    candidate = directory / MANIFEST_FILENAME
    return candidate if candidate.is_file() else None


def has_manifest(directory: Path) -> bool:
    return find_manifest(directory) is not None


def env_name(suffix: str) -> str:
    """The canonical variable for `suffix` (`PROJECT_ROOT` -> `<prefix>_PROJECT_ROOT`)."""
    return f"{ENV_PREFIX}_{suffix}"


def env(suffix: str, default: str = "", environ: MutableMapping[str, str] | None = None) -> str:
    """The value of the kit variable `suffix` (a former prefix is no longer read: `validate` names it)."""
    environ = os.environ if environ is None else environ
    value = environ.get(env_name(suffix))
    return default if value is None else value


def adopt_legacy_env(environ: MutableMapping[str, str] | None = None) -> list[str]:
    """Since 2.0.0 nothing is adopted: a former-prefixed variable is not read (the shells still call
    this through `context`, which answers no changes). Returns the former names that are set."""
    environ = os.environ if environ is None else environ
    return sorted(k for k in environ if LEGACY_ENV_PREFIX and k.startswith(LEGACY_ENV_PREFIX + "_"))


def manifest_field(manifest: dict[str, Any], dotted: str) -> Any:
    """`dotted` read from `manifest` (a former field is not read since 2.0.0: `validate` names it)."""
    return _dig(manifest, dotted)


def with_current_fields(manifest: dict[str, Any]) -> dict[str, Any]:
    """The manifest as read: since 2.0.0 a former field is not carried here (`migrate --apply` renames
    it, `validate` refuses it)."""
    import copy

    return copy.deepcopy(manifest)


def legacy_names_in(root: Path, manifest: dict[str, Any], environ: MutableMapping[str, str] | None = None) -> list[str]:
    """Every former name a host still carries: a manifest under a former filename, a former field, a
    former-prefixed variable -- each a `validate` error naming `migrate`."""
    environ = os.environ if environ is None else environ
    out = [f"{name}: a former manifest filename (now {MANIFEST_FILENAME})" for name in LEGACY_MANIFEST_FILENAMES
           if (root / name).is_file()]
    out += [f"{MANIFEST_FILENAME}: {old} is the former name of {new}" for old, new in LEGACY_MANIFEST_FIELDS.items()
            if _dig(manifest, old) is not None]
    out += [f"${k}: the former prefix {LEGACY_ENV_PREFIX}_ (now {ENV_PREFIX}_)" for k in adopt_legacy_env(environ)]
    return out


def _dig(data: Any, dotted: str) -> Any:
    for part in dotted.split("."):
        if not isinstance(data, dict) or part not in data:
            return None
        data = data[part]
    return data


def notice(old: str, new: str) -> None:
    """One line, once per legacy name and process tree: what is deprecated, what replaces it,
    when it stops. The names already told are carried in the environment, so a child process
    of a run that has said it does not say it again."""
    told = env_name("NOTICED")
    seen = os.environ.get(told, "").split("|")
    if old in seen or _quiet():
        return
    os.environ[told] = "|".join([*filter(None, seen), old])
    until = f"; read until {LEGACY_REMOVED_IN}" if LEGACY_REMOVED_IN else ""
    print(f"[{KIT_NAME}] deprecated: {old} -> {new}{until}", file=sys.stderr)


def _quiet() -> bool:
    # The opt-out itself is read under both prefixes, without a notice of its own.
    return any(os.environ.get(f"{p}_NO_DEPRECATION_NOTICE") for p in (ENV_PREFIX, LEGACY_ENV_PREFIX) if p)
