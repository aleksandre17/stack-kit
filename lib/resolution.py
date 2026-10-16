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
    driver_command_runtimes,
    driver_commands,
    driver_default_role,
    driver_delivery,
    driver_deploy_kind,
    driver_home,
    driver_package_scripts,
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
    return identity.with_current_fields(manifest)


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
    kinds: dict[str, list[str]] = {}
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
        out[f"module:{mid}:driverRoot"] = str(driver_home(typ)) if typ else ""
        out[f"module:{mid}:json"] = json.dumps(cfg, sort_keys=True)
        if role:
            roles.setdefault(role, []).append(mid)
        if typ:
            types.setdefault(typ, []).append(mid)
            if driver_deploy_kind(typ):
                kinds.setdefault(driver_deploy_kind(typ), []).append(mid)
        if folder not in folders:
            folders.append(folder)
    out["modules"] = _lines(modules)
    out.update({f"role:{r}": _lines(ids) for r, ids in roles.items()})
    out.update({f"type:{t}": _lines(ids) for t, ids in types.items()})
    out.update({f"deployKind:{k}": _lines(ids) for k, ids in kinds.items()})
    out["secretsFolders"] = _lines(folders)
    out["deployBaseSecretsFolder"] = deploy_base_secrets_folder(manifest)
    out.update({f"alias:{a}": mid for a, mid in infer_cli_aliases(manifest).items()})
    return out


def deploy_base_secrets_folder(manifest: dict) -> str:
    """The secrets folder whose DEPLOY_PATH a module without its own inherits:
    `stack.deployBaseSecretsModule` when declared, else the primary API module's folder, else none.
    No folder is spelled here -- a folder is the project's word (ADR-001 amendment 7)."""
    from lib.compose_identity import primary_api_module_id

    declared = (manifest.get("stack") or {}).get("deployBaseSecretsModule")
    if declared:
        return str(declared)
    mods = manifest.get("modules") or {}
    primary = primary_api_module_id(manifest, [str(m) for m in mods])
    return str((mods.get(primary) or {}).get("secretsModule") or primary or "") if primary else ""


def _drivers() -> dict[str, str]:
    """What each registered driver declares: its commands (and their scripts), its default role,
    its watch tasks, its host-run script, its layout simulator -- the registry, read once."""
    out: dict[str, str] = {}
    registry = {k: v for k, v in driver_registry().items() if isinstance(v, dict)}
    out["drivers"] = _lines(sorted(registry))
    from lib import catalogs
    from lib.modules import lifecycle_steps, optional_steps

    out["lifecycle:steps"] = _lines(lifecycle_steps())
    out["lifecycle:optional"] = _lines(optional_steps())
    out["environments"] = _lines(catalogs.ids("environments"))
    out["environment:run"] = catalogs.default_environment("run")
    out["environment:deploy"] = catalogs.default_environment("deploy")
    out["roles"] = _lines(catalogs.ids("roles"))
    out["roles:bootOrder"] = _lines(catalogs.ordered("roles", "bootOrder"))
    from lib.modules import script_runtimes

    runtimes = script_runtimes()
    out["runtimes"] = _lines(runtimes)
    for rid, spec in runtimes.items():
        out[f"runtime:{rid}:match"] = _lines(spec.get("match") or [])
        if spec.get("inSession"):
            out[f"runtime:{rid}:inSession"] = "true"
        if spec.get("argv"):
            out[f"runtime:{rid}:argv"] = json.dumps(spec["argv"])
    for typ, entry in registry.items():
        home = driver_home(typ)
        commands = driver_commands(typ)
        out[f"driver:{typ}:commands"] = _lines(sorted(commands))
        for name, path in commands.items():
            out[f"driver:{typ}:command:{name}"] = str(path)
        for name, runtime in driver_command_runtimes(typ).items():
            out[f"driver:{typ}:commandRuntime:{name}"] = runtime
        out[f"driver:{typ}:defaultRole"] = driver_default_role(typ)
        for name, argv in (entry.get("tasks") or {}).items():
            if isinstance(argv, list):
                out[f"driver:{typ}:task:{name}"] = _lines(argv)
        for step, name in driver_package_scripts(typ).items():
            out[f"driver:{typ}:packageScript:{step}"] = name
        script = (entry.get("hybrid") or {}).get("script")
        if script:
            out[f"driver:{typ}:hybridScript"] = str(home / script)
        simulator = layout_simulator_for_type(typ)
        if simulator:
            out[f"driver:{typ}:layoutSimulator"] = simulator
        ladder = driver_delivery(typ)
        out[f"driver:{typ}:rungs"] = _lines(ladder)
        for rung, how in ladder.items():
            out[f"driver:{typ}:rung:{rung}"] = json.dumps(how, sort_keys=True)
        for word, rewrite in (entry.get("operands") or {}).items():
            if isinstance(rewrite, dict) and isinstance(rewrite.get("to"), list):
                out[f"driver:{typ}:operand:{word}"] = json.dumps(rewrite, sort_keys=True)
    return out


def monorepo_root(root: Path) -> str:
    return (os.environ.get("OPS_MONOREPO_ROOT") or identity.env("MONOREPO_ROOT") or str(root))


# ── the environment's answers: asked each time ──────────────────────────────


def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", (text or "").strip()).strip("-").lower()
    return s or "app"


#: The deploy.env keys a declared target answers instead (ADR-001 amendment 9): the server, its base,
#: a folder's remote directory, the layout switches, and the ssh settings `ssh-args` now owns.
TARGET_KEYS = frozenset({"DEPLOY_SERVER", "DEPLOY_SERVER_BASE", "DEPLOY_PATH", "DEPLOY_LAYOUT",
                         "DEPLOY_PATH_MODE", "DEPLOY_SSH_CONFIG_FILE", "DEPLOY_SSH_IDENTITY_FILE",
                         "DEPLOY_SSH_OPTIONS"})
#: The remote-path kinds a delivery script asks for, and the layout place each is: a container's
#: (runtime), a static module's and a compose deploy's directory are all the service's unit; a
#: module's base is its environment's tree. `compose-dev`/`compose-prod` name the environment.
REMOTE_KINDS = {"module": "environment", "runtime": "unit", "static": "unit", "compose": "unit",
                "workspace": "workspace", "logs": "logs", "unit": "unit", "project": "project"}


class Resolver:
    """The environment's answers for one project root."""

    def __init__(self, start: Path | None = None) -> None:
        self.ctx = context(start)
        if "root" not in self.ctx:
            raise FileNotFoundError(f"project root not found ({identity.MANIFEST_FILENAME} required)")
        self.root = Path(self.ctx["root"])
        self.secrets_root = Path(self.ctx["secretsRoot"])
        self._target: tuple[str, dict] | None | bool = False

    @property
    def manifest(self) -> dict:
        return load_manifest(self.root)

    # ── deploy targets (ADR-001 amendment 9): declared, selected, never inferred ──

    def target(self) -> tuple[str, dict] | None:
        """(name, target) of the selected declared target -- `--target` (STACK_KIT_TARGET), else the
        environment's default (STACK_KIT_ENVIRONMENT, default prod), else the only one -- or None when
        the host declares none (the deprecated deploy.env path)."""
        if self._target is False:
            from lib import targets

            data = targets.load(self.root, self.manifest)
            self._target = None if data is None else targets.select(
                data, identity.env("TARGET"), identity.env("ENVIRONMENT"))
        return self._target  # type: ignore[return-value]

    def targets_declared(self) -> bool:
        """Whether the host declares deploy targets at all -- asked without selecting or reaching one."""
        from lib import targets

        return targets.declared_file(self.manifest) is not None

    def _target_answer(self, key: str, folder: str = "") -> str | None:
        """A deploy.env key, answered by the selected target; None when no target is declared.

        A declared target that is pending, unreachable or not selectable answers "" -- it never
        raises here. Many local steps read these keys only incidentally (a toolkit loading its
        settings for a build), and a local step never needs a deploy target; the refusal stands
        where a deploy does need one: `remote-path`, the remote preflight, `targets --verify`."""
        if key not in TARGET_KEYS or not self.targets_declared():
            return None
        from lib import targets

        try:
            return self._target_value(key, folder)
        except targets.TargetError:
            return ""

    def _target_value(self, key: str, folder: str) -> str:
        from lib import targets

        name, t = self.target()
        if key == "DEPLOY_SERVER":
            return targets.server(name, t)
        if key == "DEPLOY_SERVER_BASE":
            return str(targets.reachable(name, t)["root"]).rstrip("/")
        if key == "DEPLOY_PATH":
            if not folder:
                return ""
            env = (identity.env("ENVIRONMENT") or self._deploy_default())
            kind = "infra" if folder == "infra" else "environment"
            return targets.render(t, kind, project=self.project_slug(), environment=env, folder=folder,
                                  infra_slug=self.infra_slug(), manifest=self.manifest)
        if key == "DEPLOY_LAYOUT":
            return "structured"
        if key == "DEPLOY_PATH_MODE":
            return "base"
        return ""  # DEPLOY_SSH_*: the target's ssh is `ssh-args`'

    def _deploy_default(self) -> str:
        from lib import catalogs

        return catalogs.default_environment("deploy", self.manifest)

    def remote_path(self, folder: str, kind: str, container: str, environment: str = "",
                    service: str = "") -> str:
        """Where one deploy unit of a module lives on the target: the target's layout over the kit's
        default; without a declared target, the deprecated DEPLOY_PATH/DEPLOY_LAYOUT reading."""
        environment = environment or self._deploy_default()
        # `compose-<environment>` names the environment (any the catalog declares).
        if kind.startswith("compose-"):
            from lib import catalogs

            environment = catalogs.require("environments", kind.split("-", 1)[1], self.manifest, what="remote-path")
            kind = "compose"
        if kind not in REMOTE_KINDS:
            raise ValueError(f"no remote kind '{kind}' (kinds: {', '.join(REMOTE_KINDS)}, compose-<environment>)")
        chosen = self.target()
        if chosen is not None:
            from lib import targets

            name, t = chosen
            targets.reachable(name, t)
            return targets.render(t, REMOTE_KINDS[kind], project=self.project_slug(), folder=folder,
                                  container=container, environment=environment, service=service or container, manifest=self.manifest)
        from lib import deploy_paths

        # A folder without its own DEPLOY_PATH inherits the deploy-base folder's (workers the API's).
        inherit = self.ctx.get("deployBaseSecretsFolder", "")
        base = (self.env_value(folder, "DEPLOY_PATH").rstrip("/")
                or (self.env_value(inherit, "DEPLOY_PATH").rstrip("/") if inherit and inherit != folder else "")
                or self.deploy_base(folder))
        layout = self.env_value(folder, "DEPLOY_LAYOUT")
        mode = self.env_value(folder, "DEPLOY_PATH_MODE") or "base"
        if kind == "module":
            return base
        if kind in ("runtime", "workspace"):
            return deploy_paths.resolve_backend_deploy_path(base=base, container_name=container, kind=kind,
                                                            layout=layout or "flat", path_mode=mode)
        front = "static" if kind == "static" else ("compose-dev" if environment == "dev" else "compose-prod")
        return deploy_paths.resolve_module_deploy_path(base=base, container_name=container, kind=front,
                                                       layout=layout or "structured", path_mode=mode)

    def ssh_args(self) -> list[str]:
        """The openssh options every ssh, scp and rsync of a deploy takes: the target's (port, strict
        host keys against its pinned file, its identity reference, options); without a target, the
        deprecated DEPLOY_SSH_CONFIG_FILE / DEPLOY_SSH_IDENTITY_FILE / DEPLOY_SSH_OPTIONS."""
        if self.targets_declared():
            # No options for a target nothing can reach (pending, unselected): the deploy that needs
            # it is refused at its preflight, naming why; a local step loading ssh helpers is not.
            from lib import targets

            try:
                name, t = self.target()
                targets.reachable(name, t)
            except targets.TargetError:
                return []
            return targets.ssh_args(self.root, name, t)  # a reachable target's own error is said
        out: list[str] = []
        for key, flag in (("DEPLOY_SSH_CONFIG_FILE", "-F"), ("DEPLOY_SSH_IDENTITY_FILE", "-i")):
            value = self.deploy_env_value(key)
            if value:
                path = Path(value) if Path(value).is_absolute() else Path(self.ctx["monorepoRoot"]) / value
                if path.is_file():
                    out += [flag, path.as_posix()]
        out += self.deploy_env_value("DEPLOY_SSH_OPTIONS").split()
        return out

    def compose_project(self, environment: str = "") -> str:
        """The compose project a deploy runs under: `{project}-{environment}` on a declared target;
        "" without one (the deprecated path keeps compose's own default). It names the project's
        environment, not a server, so it is answered without selecting or reaching a target."""
        if not self.targets_declared():
            return ""
        from lib import targets

        return targets.compose_project(self.project_slug(), environment or (identity.env("ENVIRONMENT") or self._deploy_default()))

    def remote_preflight(self, services: list[str]) -> str:
        """The server-side preflight of a deploy (ownership marker, foreign ports); "" without a target."""
        chosen = self.target()
        if chosen is None:
            return ""
        from lib import targets

        name, t = chosen
        targets.reachable(name, t)
        return targets.preflight(t, project=self.project_slug(), environment=(identity.env("ENVIRONMENT") or self._deploy_default()),
                                 repository=targets.repository_identity(self.root), services=services)

    def confined(self, path: str) -> bool:
        """Whether a remote path lies inside this project's directory on the target (no target: the
        deprecated path has no project directory to hold, and is not judged)."""
        chosen = self.target()
        if chosen is None:
            return True
        from lib import targets

        project_dir = targets.render(chosen[1], "project", project=self.project_slug())
        import posixpath

        return targets._under(posixpath.normpath(path), project_dir) and posixpath.normpath(path) != project_dir

    def module_deploy_units(self) -> list[tuple[str, str, str]]:
        """(module, secrets folder, container) for every module -- what `targets --plan` renders."""
        from lib.compose_identity import load_deploy_env, resolve_module_service_name

        deploy = load_deploy_env(self.secrets_root)
        out = []
        for mid, cfg in (self.manifest.get("modules") or {}).items():
            if isinstance(cfg, dict):
                out.append((mid, str(cfg.get("secretsModule") or mid),
                            resolve_module_service_name(mid, self.manifest, deploy, self.root.name)))
        return out

    def folders(self) -> list[str]:
        return [f for f in self.ctx.get("secretsFolders", "").split("\n") if f]

    def env_files(self, folder: str, profile: str = "all") -> list[Path]:
        from lib import catalogs

        return envfile.folder_files(self.secrets_root, folder, profile, catalogs.ids("environments", self.manifest))

    def env_value(self, folder: str, key: str, default: str = "") -> str:
        """The last non-empty value of `key` across the folder's env files, as compose would apply it
        -- except a deploy key a declared target answers (TARGET_KEYS): the target is its one home."""
        answered = self._target_answer(key, folder)
        if answered is not None:
            return answered or default
        return envfile.merged(self.env_files(folder)).get(key, default)

    def run_env(self, folder: str, environment: str = "") -> dict[str, str]:
        """The variables a run of the folder's module sets, for one environment (envfile.run_files);
        the catalog's run default when none is asked for."""
        from lib import catalogs

        envs = catalogs.ids("environments", self.manifest)
        environment = environment or catalogs.default_environment("run", self.manifest)
        return envfile.merged(envfile.run_files(self.secrets_root, folder, environment, envs))

    def deploy_env_value(self, key: str, default: str = "") -> str:
        """A declared target's answer for a deploy key; else an operator's process environment, then
        the shared deploy.env (the deprecated home of the server, ADR-001 amendment 9)."""
        answered = self._target_answer(key)
        if answered is not None:
            return answered or default
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
        """The target's root. Without a declared target (deprecated): DEPLOY_SERVER_BASE, else the
        `/home/<user>` of DEPLOY_SERVER -- an inference kept only until a host declares its targets,
        and gone at 2.0.0 (`migrate --apply` writes the root it finds, and invents none)."""
        if self.targets_declared():
            return self.deploy_env_value("DEPLOY_SERVER_BASE")
        base = self.deploy_env_value("DEPLOY_SERVER_BASE") or self._any_folder("DEPLOY_SERVER_BASE")
        if base:
            return base
        server = self.deploy_env_value("DEPLOY_SERVER") or self._any_folder("DEPLOY_SERVER")
        m = re.match(r"^([^@]+)@", server)
        return f"/home/{m.group(1)}" if m else ""

    def infra_slug(self) -> str:
        return slugify(self.env_value("infra", "INFRA_SLUG") or Path(self.ctx["monorepoRoot"]).name)

    def infra_deploy_path(self) -> str:
        if self.targets_declared():
            return self.env_value("infra", "DEPLOY_PATH")
        from lib.deploy_paths import resolve_infra_deploy_path

        return resolve_infra_deploy_path(deploy_path=self.env_value("infra", "DEPLOY_PATH") or None,
                                         server_base=self.server_base() or None,
                                         global_project=self.project_slug(),
                                         consumer_slug=self.infra_slug())

    def deploy_base(self, folder: str) -> str:
        """A folder's remote base: the target's module directory; without a target (deprecated), its
        DEPLOY_PATH, else {server base}/{project slug}/{folder}."""
        if self.targets_declared():
            return self.env_value(folder, "DEPLOY_PATH")
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
