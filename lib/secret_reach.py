"""A generated secret must reach the app it is made for -- checked, not assumed (ADR-001 amendment 20).

The kit makes a generated secret on the server and hands it to the container in the form the module's
driver declares (`generatedSecrets`): a directory of key-per-file values under one env name, or the
`<NAME>_FILE` convention. Neither form is read by a runtime on its own -- an app reads it only if its
code says so. A driver declares what that code looks like (`generatedSecrets.reads`: a glob and a
pattern), and a module that is given a generated secret while nothing in its source matches is
refused: the secret would be made, mounted and ignored, and the app would run on whatever value it
found elsewhere -- a committed one, in the case that found this.

A driver that declares no `reads` cannot be checked, and is warned about rather than passed.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from lib import config_policy
from lib.delivery import model


def _generated_for(catalogue: dict[str, Any], folder: str, folders: set[str]) -> list[str]:
    out = []
    for row in catalogue.get("keys") or []:
        if not isinstance(row, dict) or not config_policy.generate_bytes(row):
            continue
        policy = row.get("policy") if isinstance(row.get("policy"), dict) else {}
        named = policy.get("modules") or []
        if folder in named or (not named and len(folders) <= 1):
            out.append(str(row.get("key")))
    return out


def problems(root: Path, manifest: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(errors, warnings) for every module given a generated secret its code does not read."""
    catalogue = config_policy.catalogue_of(root, manifest)
    try:
        services = [s for s in model.all_services(manifest) if s.module]
    except (ValueError, model.ModelError):
        return [], []  # a manifest that cannot name its services is refused by the checks that own that
    folders = {s.secrets_folder for s in services if s.secrets_folder}
    errors, warnings = [], []
    for service in services:
        keys = _generated_for(catalogue, service.secrets_folder, folders)
        if not keys:
            continue
        declared = service.spec.get("generatedSecrets") or {}
        form = (f"the directory named by {declared['directoryEnv']}" if declared.get("directoryEnv")
                else "<NAME>_FILE")
        reads = declared.get("reads")
        if not reads:
            warnings.append(f"modules.{service.module}: is given {', '.join(keys)} as {form}, and its driver "
                            f"declares no way to see that the code reads it -- make sure it does")
            continue
        base = root / str((manifest.get("modules") or {}).get(service.module, {}).get("path") or "")
        pattern = re.compile(str(reads["pattern"]))
        found = any(pattern.search(path.read_text(encoding="utf-8", errors="replace"))
                    for path in base.glob(str(reads["glob"])) if path.is_file()
                    and not any(part in {"bin", "obj", "node_modules", "dist"} for part in path.parts))
        if not found:
            errors.append(f"modules.{service.module}: is given {', '.join(keys)} as {form}, and nothing in "
                          f"{reads['glob']} under {base.relative_to(root).as_posix()} matches {reads['pattern']!r}: "
                          f"the secret would be made and ignored. {reads.get('how', '')}".rstrip())
    return errors, warnings
