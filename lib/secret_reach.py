"""A generated secret must reach the app it is made for -- checked, not assumed (ADR-001 amendment 20).

The kit makes a generated secret on the server and hands it to the container in the form the module's
driver declares (`generatedSecrets`): a directory of key-per-file values under one env name, or the
`<NAME>_FILE` convention. Neither form is read by a runtime on its own -- an app reads it only if its
code says so. A driver declares what that code looks like (`generatedSecrets.reads`: a glob -- or
several -- and a pattern), and what it looks like in the built output a release carries
(`reads.built`, the same shape). It is checked three times, each where the code it reads is:

    validate   the module's source -- a module given a generated secret its code never reads is refused
    release    the release's own built output -- so a package of another commit (`--artifact`) is held too
    rollback   the release on the server -- a release made before its code read the secret is refused,
               since it would run on whatever value it found elsewhere (a committed one, in the case
               that found this)

A driver that declares no `reads` cannot be given a generated secret: the kit could not see that it is
read. The check is static -- it proves the code names the reader, not that the reader is called; that
the app starts on the generated value is proved by the host's own test and by health after a release.
"""

from __future__ import annotations

import fnmatch
import posixpath
import re
from pathlib import Path
from typing import Any

from lib import config_policy
from lib.delivery import model

#: What a toolchain writes inside a module: never the module's own code.
OUTPUTS = {"bin", "obj", "node_modules", "dist"}


def _globs(spec: dict[str, Any]) -> list[str]:
    value = spec.get("glob")
    return [value] if isinstance(value, str) else [str(g) for g in value or []]


def _matches(rel: str, globs: list[str]) -> bool:
    """A posix path against globs; a leading `**/` also matches at the top."""
    return any(fnmatch.fnmatch(rel, g) or (g.startswith("**/") and fnmatch.fnmatch(rel, g[3:])) for g in globs)


def _form(declared: dict[str, Any]) -> str:
    return f"the directory named by {declared['directoryEnv']}" if declared.get("directoryEnv") else "<NAME>_FILE"


def keys_of(root: Path, manifest: dict[str, Any], service: model.Service) -> list[str]:
    """The generated keys this service is given -- the same set the release makes and hands over."""
    catalogue = config_policy.catalogue_of(root, manifest)
    return [str(r.get("key")) for r in config_policy.generated_rows(catalogue, service.secrets_folder, manifest)]


def _unread(service: model.Service, keys: list[str]) -> str:
    declared = service.spec.get("generatedSecrets") or {}
    return (f"modules.{service.module}: is given {', '.join(keys)} as {_form(declared)}, and its driver "
            f"({service.driver or 'none'}) declares no way to see that code reads one (`generatedSecrets.reads`) -- "
            f"scope the key to a module that reads it (`policy.modules`), or declare how this runtime reads it")


def problems(root: Path, manifest: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(errors, warnings) for validate: every module given a generated secret its source does not read."""
    try:
        services = [s for s in model.all_services(manifest) if s.module]
    except (ValueError, model.ModelError):
        return [], []  # a manifest that cannot name its services is refused by the checks that own that
    errors: list[str] = []
    for service in services:
        keys = keys_of(root, manifest, service)
        if not keys:
            continue
        declared = service.spec.get("generatedSecrets") or {}
        reads = declared.get("reads")
        if not reads:
            errors.append(_unread(service, keys))
            continue
        base = root / str((manifest.get("modules") or {}).get(service.module, {}).get("path") or "")
        pattern = re.compile(str(reads["pattern"]))
        found = any(pattern.search(path.read_text(encoding="utf-8", errors="replace"))
                    for glob in _globs(reads) for path in base.glob(glob)
                    if path.is_file() and not OUTPUTS & set(path.relative_to(base).parts))
        if not found:
            errors.append(f"modules.{service.module}: is given {', '.join(keys)} as {_form(declared)}, and nothing in "
                          f"{', '.join(_globs(reads))} under {base.relative_to(root).as_posix()} matches "
                          f"{reads['pattern']!r}: the secret would be made and ignored. {reads.get('how', '')}".rstrip())
    return errors, []


def release_problems(root: Path, manifest: dict[str, Any], services: list[model.Service],
                     trees: dict[str, dict[str, bytes]]) -> list[str]:
    """Why a release's own built output would ignore a generated secret its service is given -- one line
    per service. A driver whose built output cannot be read (`reads.built` undeclared: a compressed
    archive) is held by validate's source check only."""
    out = []
    for service in services:
        keys = keys_of(root, manifest, service)
        if not keys:
            continue
        reads = (service.spec.get("generatedSecrets") or {}).get("reads")
        if not reads:
            out.append(_unread(service, keys))
            continue
        built = reads.get("built")
        if not built:
            continue
        pattern = re.compile(str(built["pattern"]).encode("utf-8"))
        files = trees.get(service.id) or {}
        if not any(pattern.search(data) for rel, data in files.items() if _matches(rel, _globs(built))):
            out.append(f"{service.id}: is given {', '.join(keys)}, and nothing this release built "
                       f"({', '.join(_globs(built))}) matches {built['pattern']!r} -- it would run without it")
    return out


def server_problem(ctx, service: model.Service, rid: str) -> str:
    """Why release `rid` on the server would ignore a generated secret its service is given ("" when it
    reads it, or when the driver's built output cannot be read)."""
    keys = keys_of(ctx.root, ctx.manifest, service)
    built = ((service.spec.get("generatedSecrets") or {}).get("reads") or {}).get("built")
    if not keys or not built:
        return ""
    where = posixpath.join(ctx.places.of("releases", service), rid)
    for glob in _globs(built):
        found = ctx.transport.exec(["grep", "-rqaE", str(built["pattern"]), f"--include={glob.split('/')[-1]}", where],
                                   readonly=True)
        if found.code == 0:
            return ""
    return (f"its built output does not read {', '.join(keys)} (nothing matches {built['pattern']!r}) -- it was made "
            f"before its code read the generated secret, and would run on whatever value it found elsewhere")
