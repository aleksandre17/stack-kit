"""The one resolver (ADR-001 decision 2).

Before this module the same resolution lived three times -- Python, `lib/project.sh` + `lib/env.sh`
and `lib/project.ps1` + `lib/env.ps1` -- and the copies had drifted apart where nobody could see it:
bash inferred a module's role from two driver names spelled inline while Python read the registry;
PowerShell fell back to ANY field of the scaffold template, so a host module named like a template
sample silently inherited the sample's values; a module env value was the FIRST file's in bash and
the LAST file's in PowerShell; a deploy value preferred the file in bash and the process environment
in PowerShell; each runtime searched for the project in its own order.

Here each rule has one home, and the shells hold none: they ask this module, through
`lib/resolve_cli.py`, and read the answer.

Two kinds of answer, kept apart on purpose:

* **The context** -- what the MANIFEST says: the project root, every scalar field and list, the
  declared convention defaults, the modules with their type, role, paths and credentials, roles,
  types, aliases. A pure function of the manifest and the kit, so a shell may cache it for its
  lifetime. It is FLAT: one map of `kind:key` to text, identical in every runtime, so parity
  between runtimes is a comparison of two maps.
* **The environment's answers** -- env files, env values, slugs, the server base, deploy paths.
  They read env files and the process environment, which change during a run, so they are asked
  for each time and never cached.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Iterator

from lib import envfile, identity
from lib.credentials import module_credentials
from lib.manifest_defaults import flatten_defaults
from lib.modules import (
    driver_default_role,
    driver_registry,
    infer_cli_aliases,
    layout_simulator_for_type,
    module_role,
)
from lib.project_context import find_project_root, load_manifest

KIT_ROOT = Path(__file__).resolve().parents[1]



# ── the context: what the manifest says ─────────────────────────────────────


def _leaves(data: dict[str, Any], prefix: str = "") -> Iterator[tuple[str, Any]]:
    for key, value in data.items():
        dotted = f"{prefix}{key}"
        if isinstance(value, dict):
            yield from _leaves(value, dotted + ".")
        else:
            yield dotted, value


def _text(value: Any) -> str:
    return str(value)


def _normalized(manifest: dict[str, Any]) -> dict[str, Any]:
    """The manifest with every field the kit renamed under its current name (the former noticed)."""
    import copy

    out = copy.deepcopy(manifest)
    for old, new in identity.LEGACY_MANIFEST_FIELDS.items():
        if identity._dig(out, new) is not None:
            continue
        value = identity.manifest_field(out, new)
        if value is None:
            continue
        node = out
        *parent, leaf = new.split(".")
        for part in parent:
            node = node.setdefault(part, {})
        node[leaf] = value
    return out


def _lines(items) -> str:
    return "\n".join(str(i) for i in items)


def _root(start: Path | None) -> Path | None:
    try:
        return find_project_root(start)
    except FileNotFoundError:
        return None


def context(start: Path | None = None) -> dict[str, str]:
    """Everything the manifest says, as one flat map of `kind:key` to text.

    Kinds: `identity:` the kit's declared names; `root`, `manifest`, `kitRoot`, `packageRoot`,
    `monorepoRoot`, `secretsRoot`; `path:` derived project paths; `field:` every scalar leaf;
    `list:` every list of scalars (newline-joined); `default:` the declared convention defaults;
    `feature:` true/false; `module:<id>:<attr>`; `modules`, `role:<role>`, `type:<type>`,
    `secretsFolders` (newline-joined ids); `alias:<alias>`.
    """
    out: dict[str, str] = {f"identity:{k}": v for k, v in identity._DECLARATION.items()
                           if isinstance(v, str) and not k.startswith("$")}
    out["kitRoot"] = str(KIT_ROOT)
    out["packageRoot"] = os.environ.get("OPS_PACKAGE_ROOT") or str(KIT_ROOT)
    for dotted, value in flatten_defaults().items():
        out[f"default:{dotted}"] = value
    out.update(_drivers())
    root = _root(start)
    if root is None:
        return out
    found = identity.find_manifest(root)
    manifest = _normalized(load_manifest(root))
    out["root"] = str(root)
    out["manifest"] = str(found) if found else ""
    out["monorepoRoot"] = monorepo_root(root)

    for dotted, value in _leaves(manifest):
        if isinstance(value, list):
            if all(not isinstance(i, (dict, list)) for i in value):
                out[f"list:{dotted}"] = _lines(str(i).strip() for i in value
                                               if i is not None and str(i).strip())
        elif value is not None:
            out[f"field:{dotted}"] = _text(value)

    def field(dotted: str) -> str:
        return out.get(f"field:{dotted}") or out.get(f"default:{dotted}", "")

    secrets_root = root / field("secrets")
    out["secretsRoot"] = str(secrets_root)
    out["secretsRel"] = field("secrets").replace("\\", "/")
    out["path:stackComposeDir"] = str(root / field("stack.composeDir"))
    out["path:infraComposeDir"] = str(root / (field("stack.infraComposeDir") or "ops/compose/infra"))
    out["path:composeCatalog"] = str(root / field("compose.catalog"))
    out["path:syncModules"] = str(root / field("compose.syncModules"))

    for name, value in (manifest.get("features") or {}).items():
        out[f"feature:{name}"] = "true" if value is True else "false"

    modules = {str(k): v for k, v in (manifest.get("modules") or {}).items() if isinstance(v, dict)}
    roles: dict[str, list[str]] = {}
    types: dict[str, list[str]] = {}
    folders: list[str] = []
    for mid, cfg in modules.items():
        typ = str(cfg.get("type") or "")
        role = module_role(manifest, mid)
        folder = str(cfg.get("secretsModule") or mid)
        out[f"module:{mid}:type"] = typ
        out[f"module:{mid}:role"] = role
        out[f"module:{mid}:path"] = str(root / cfg["path"]) if cfg.get("path") else ""
        out[f"module:{mid}:secretsFolder"] = folder
        out[f"module:{mid}:secretsDir"] = str(secrets_root / folder)
        out[f"module:{mid}:credentials"] = _lines(
            "\t".join((c["file"], c["mount"], c.get("envVar", ""))) for c in module_credentials(manifest, mid))
        out[f"module:{mid}:driverRoot"] = str(KIT_ROOT / "drivers" / typ) if typ else ""
        out[f"module:{mid}:json"] = json.dumps(cfg, sort_keys=True)
        if role:
            roles.setdefault(role, []).append(mid)
        if typ:
            types.setdefault(typ, []).append(mid)
        if folder not in folders:
            folders.append(folder)
    out["modules"] = _lines(modules)
    out.update({f"role:{r}": _lines(ids) for r, ids in roles.items()})
    out.update({f"type:{t}": _lines(ids) for t, ids in types.items()})
    out["secretsFolders"] = _lines(folders)
    out.update({f"alias:{a}": mid for a, mid in infer_cli_aliases(manifest).items()})
    return out


def _drivers() -> dict[str, str]:
    """What each registered driver declares: its commands (and their scripts), its default role,
    its watch tasks, its host-run script, its layout simulator -- the registry, read once."""
    out: dict[str, str] = {}
    registry = {k: v for k, v in driver_registry().items() if isinstance(v, dict)}
    out["drivers"] = _lines(sorted(registry))
    for typ, entry in registry.items():
        home = KIT_ROOT / "drivers" / typ
        commands = entry.get("commands") or {}
        out[f"driver:{typ}:commands"] = _lines(sorted(commands))
        for name, rel in commands.items():
            out[f"driver:{typ}:command:{name}"] = str(home / rel)
        out[f"driver:{typ}:defaultRole"] = driver_default_role(typ)
        for name, argv in (entry.get("tasks") or {}).items():
            if isinstance(argv, list):
                out[f"driver:{typ}:task:{name}"] = _lines(argv)
        script = (entry.get("hybrid") or {}).get("script")
        if script:
            out[f"driver:{typ}:hybridScript"] = str(home / script)
        simulator = layout_simulator_for_type(typ)
        if simulator:
            out[f"driver:{typ}:layoutSimulator"] = simulator
    return out


def monorepo_root(root: Path) -> str:
    return (os.environ.get("OPS_MONOREPO_ROOT") or identity.env("MONOREPO_ROOT") or str(root))


# ── the environment's answers: asked each time ──────────────────────────────


def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", (text or "").strip()).strip("-").lower()
    return s or "app"


class Resolver:
    """The environment's answers for one project root."""

    def __init__(self, start: Path | None = None) -> None:
        self.ctx = context(start)
        if "root" not in self.ctx:
            raise FileNotFoundError(f"project root not found ({identity.MANIFEST_FILENAME} required)")
        self.root = Path(self.ctx["root"])
        self.secrets_root = Path(self.ctx["secretsRoot"])

    def folders(self) -> list[str]:
        return [f for f in self.ctx.get("secretsFolders", "").split("\n") if f]

    def env_files(self, folder: str, profile: str = "all") -> list[Path]:
        return envfile.folder_files(self.secrets_root, folder, profile)

    def env_value(self, folder: str, key: str, default: str = "") -> str:
        """The last non-empty value of `key` across the folder's env files, as compose would apply it."""
        return envfile.merged(self.env_files(folder)).get(key, default)

    def deploy_env_value(self, key: str, default: str = "") -> str:
        """An operator's process environment first, then the shared deploy.env."""
        return os.environ.get(key) or envfile.parse(self.secrets_root / "deploy.env").get(key) or default

    def _any_folder(self, key: str) -> str:
        for folder in self.folders():
            value = self.env_value(folder, key)
            if value:
                return value
        return ""

    def project_slug(self) -> str:
        return slugify(self.deploy_env_value("DEPLOY_PROJECT") or Path(self.ctx["monorepoRoot"]).name)

    def compose_slug(self) -> str:
        return slugify(self.deploy_env_value("COMPOSE_PROJECT_NAME") or Path(self.ctx["monorepoRoot"]).name)

    def docker_network(self) -> str:
        return (self.deploy_env_value("DOCKER_NETWORK")
                or self.deploy_env_value(identity.env_name("DOCKER_NETWORK"))
                or f"{self.compose_slug()}-net")

    def server_base(self) -> str:
        base = self.deploy_env_value("DEPLOY_SERVER_BASE") or self._any_folder("DEPLOY_SERVER_BASE")
        if base:
            return base
        server = self.deploy_env_value("DEPLOY_SERVER") or self._any_folder("DEPLOY_SERVER")
        m = re.match(r"^([^@]+)@", server)
        return f"/home/{m.group(1)}" if m else ""

    def infra_slug(self) -> str:
        return slugify(self.env_value("infra", "INFRA_SLUG") or Path(self.ctx["monorepoRoot"]).name)

    def infra_deploy_path(self) -> str:
        from lib.deploy_paths import resolve_infra_deploy_path

        return resolve_infra_deploy_path(deploy_path=self.env_value("infra", "DEPLOY_PATH") or None,
                                         server_base=self.server_base() or None,
                                         global_project=self.project_slug(),
                                         consumer_slug=self.infra_slug())

    def deploy_base(self, folder: str) -> str:
        """A folder's remote base: its DEPLOY_PATH, else {server base}/{project slug}/{folder}."""
        explicit = self.env_value(folder, "DEPLOY_PATH").rstrip("/")
        if explicit:
            return explicit
        base = self.server_base()
        if not base:
            raise ValueError(f"no DEPLOY_PATH for '{folder}' and no DEPLOY_SERVER_BASE or DEPLOY_SERVER "
                             "to derive one from")
        return f"{base.rstrip('/')}/{self.project_slug()}/{folder}"

    # ── infra compose: which files, which tunnels (PowerShell held these alone before) ──

    def infra_compose_dir(self) -> Path:
        return Path(self.ctx["path:infraComposeDir"])

    def _list(self, *dotted: str) -> list[str]:
        """The first of `dotted` the manifest declares as a list (a lone string counts as one)."""
        for d in dotted:
            if f"list:{d}" in self.ctx:
                return [i for i in self.ctx[f"list:{d}"].split("\n") if i]
            if self.ctx.get(f"field:{d}"):
                return [self.ctx[f"field:{d}"]]
        return []

    def infra_services(self) -> list[str]:
        return self._list("stack.infra.services", "stack.infraProfiles")

    def infra_compose_files(self) -> list[str]:
        """The compose files of the infra stack, relative to its directory: a declared override,
        else the base file and one fragment per declared service, else a single monolith."""
        d = self.infra_compose_dir()
        override = self._list("stack.infra.composeFiles", "stack.infraComposeFiles")
        if override:
            for rel in override:
                if not (d / rel).is_file():
                    raise ValueError(f"stack.infra.composeFiles missing: {d / rel}")
            return override
        if (d / "docker-compose.base.yml").is_file():
            files = ["docker-compose.base.yml"]
            for svc in self.infra_services():
                frag = f"services/{svc}.yml"
                if not (d / frag).is_file():
                    raise ValueError(f"stack.infra.services: missing fragment {frag} "
                                     "(add yaml or override stack.infra.composeFiles)")
                files.append(frag)
            return files
        if (d / "docker-compose.yml").is_file():
            return ["docker-compose.yml"]
        raise ValueError(f"No docker-compose.base.yml or docker-compose.yml under {d}")

    def infra_compose_args(self) -> list[str]:
        files = self.infra_compose_files()
        args = [a for f in files for a in ("-f", f)]
        if files == ["docker-compose.yml"]:
            args += [a for svc in self.infra_services() for a in ("--profile", svc)]
        return args

    def infra_tunnel_forwards(self) -> list[dict[str, str]]:
        from lib.infra_tunnel import load_infra_catalog, tunnel_forwards

        services = self.infra_services()
        if not services:
            raise ValueError(f"stack.infra.services is empty - declare enabled stores in "
                             f"{identity.MANIFEST_FILENAME}")
        catalog = load_infra_catalog(KIT_ROOT / "compose" / "infra-catalog.json",
                                     self.infra_compose_dir() / "infra-catalog.json")
        forwards = tunnel_forwards(service_ids=services, catalog=catalog,
                                   env_getter=lambda key, default: self.env_value("infra", key, default))
        if not forwards:
            raise ValueError("No tunnel ports for stack.infra.services - add tunnel[] to catalog modules")
        return forwards

    def infra_sync_paths(self) -> list[str]:
        """What a remote infra sync carries: the compose files, and the prod/coexist/readme beside them."""
        d = self.infra_compose_dir()
        paths = list(self.infra_compose_files())
        for extra in ("docker-compose.prod.yml", "docker-compose.coexist.yml", "README.md"):
            if (d / extra).is_file() and extra not in paths:
                paths.append(extra)
        return list(dict.fromkeys(paths))
