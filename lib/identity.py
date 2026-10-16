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
    """Every filename that may hold a project manifest — canonical first."""
    return (MANIFEST_FILENAME, *LEGACY_MANIFEST_FILENAMES)


def find_manifest(directory: Path) -> Path | None:
    """The manifest in `directory`, preferring the canonical name.

    Returns None when the directory holds no manifest under any accepted name.
    A legacy hit is announced once per name so a consumer learns it is on a
    deprecated name instead of discovering it at the next major version.
    """
    for name in manifest_filenames():
        candidate = directory / name
        if candidate.is_file():
            if name != MANIFEST_FILENAME:
                notice(name, MANIFEST_FILENAME)
            return candidate
    return None


def has_manifest(directory: Path) -> bool:
    return find_manifest(directory) is not None


def env_name(suffix: str) -> str:
    """The canonical variable for `suffix` (`PROJECT_ROOT` -> `<prefix>_PROJECT_ROOT`)."""
    return f"{ENV_PREFIX}_{suffix}"


def env(suffix: str, default: str = "", environ: MutableMapping[str, str] | None = None) -> str:
    """The value of the kit variable `suffix`: the canonical name, else the legacy one (noticed)."""
    environ = os.environ if environ is None else environ
    value = environ.get(env_name(suffix))
    if value is not None:
        return value
    if LEGACY_ENV_PREFIX:
        old = f"{LEGACY_ENV_PREFIX}_{suffix}"
        if old in environ:
            notice(old, env_name(suffix))
            return environ[old]
    return default


def adopt_legacy_env(environ: MutableMapping[str, str] | None = None) -> list[str]:
    """Carry every legacy-prefixed variable to its canonical name, once, for this process tree.

    The canonical name wins when both are set. The legacy name is then removed, so a child
    process sees one name and the notice is printed once, by the process that adopted it.
    Returns the legacy names adopted.
    """
    environ = os.environ if environ is None else environ
    if not LEGACY_ENV_PREFIX:
        return []
    adopted = []
    for old in sorted(k for k in environ if k.startswith(LEGACY_ENV_PREFIX + "_")):
        new = env_name(old[len(LEGACY_ENV_PREFIX) + 1:])
        environ.setdefault(new, environ[old])
        notice(old, new)
        del environ[old]
        adopted.append(old)
    return adopted


def manifest_field(manifest: dict[str, Any], dotted: str) -> Any:
    """`dotted` read from `manifest`, falling back to the legacy field it replaced (noticed)."""
    found = _dig(manifest, dotted)
    if found is not None:
        return found
    for old, new in LEGACY_MANIFEST_FIELDS.items():
        if new == dotted:
            legacy = _dig(manifest, old)
            if legacy is not None:
                notice(f"{MANIFEST_FILENAME}: {old}", dotted)
                return legacy
    return None


def with_current_fields(manifest: dict[str, Any]) -> dict[str, Any]:
    """A copy of `manifest` with every renamed field under its current name only (each former one
    noticed). What the schema and the resolver read, so a host on a former field is held to the
    same contract as one on the current field -- and is not refused for the spelling."""
    import copy

    out = copy.deepcopy(manifest)
    for old, new in LEGACY_MANIFEST_FIELDS.items():
        *oparent, oleaf = old.split(".")
        holder = _dig(out, ".".join(oparent)) if oparent else out
        if not isinstance(holder, dict) or oleaf not in holder:
            continue
        value = holder.pop(oleaf)
        if _dig(out, new) is not None:
            continue  # the current name is already there; it wins, as everywhere
        notice(f"{MANIFEST_FILENAME}: {old}", new)
        node = out
        *nparent, nleaf = new.split(".")
        for part in nparent:
            node = node.setdefault(part, {})
        node[nleaf] = value
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
