#!/usr/bin/env python3
"""Deploy targets: declared configuration, never a value the kit holds (ADR-001 amendment 9).

A host names a tracked, non-secret file in its manifest (`deploy.targets`); a gitignored
`<name>.local.json` beside it is merged over it, per machine. Each named target says where a deploy
goes (`host`, `user`, `port`, an absolute `root`), what runs it there (`runtime`), how ssh reaches it
(`ssh`: an identity REFERENCE, pinned host keys, options) and where each deploy unit lives (`layout`,
over the kit's one default template, `config/deploy-layout.default.json`). The kit infers nothing:
no `/home/<user>`, no fallback base, no trust on first use unless a target declares it.

This module is the one home of the rule; the resolver answers every server, ssh and remote-path
question from the selected target, and the shells only ask it.

    targets.py            each target: runtime, host, root, ssh identity kind, host-key policy
    targets.py --plan     ...and every module's remote paths per kind and environment
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

if __name__ == "__main__":  # run as a file: the kit root, not lib/, is what `lib.` resolves from
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.stdout.reconfigure(encoding="utf-8")

from lib import identity  # noqa: E402

KIT = Path(__file__).resolve().parents[1]
SCHEMA = KIT / "config" / "deploy-targets.schema.json"
DEFAULT_LAYOUT = KIT / "config" / "deploy-layout.default.json"
#: The places a layout declares (config/deploy-layout.default.json), in the order a tree prints them.
KINDS = ("project", "environment", "unit", "logs", "releases", "current", "runtime", "workspace", "stack",
         "stackEnv", "infra")


def environments(manifest: dict[str, Any] | None = None) -> list[str]:
    """The environments a target tree splits by (catalogs.environments)."""
    from lib import catalogs

    return catalogs.ids("environments", manifest)


def _workspace_envs(manifest: dict[str, Any] | None = None) -> list[str]:
    from lib import catalogs

    return catalogs.flagged("environments", "workspace", manifest)
_PLACEHOLDER = re.compile(r"\{(@?[A-Za-z]+)\}")
_VALUES = {"root", "project", "environment", "service", "container", "folder", "infraSlug"}
_ALLOWED = _VALUES | {f"@{k}" for k in KINDS}
#: Where a project's ownership is written on the server, under its project directory.
MARKER = ".stack-kit-project"
#: What may never be a value of a targets file: a key's armour, or a field that names a secret.
_SECRET_TEXT = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----|PRIVATE KEY")
_SECRET_FIELD = re.compile(r"(?i)^(password|passphrase|secret|token|private_?key|key)$")
#: ssh options host-key checking owns; a target sets them through `hostKeys`, never `options`.
_HOST_KEY_OPTIONS = {"stricthostkeychecking", "userknownhostsfile", "globalknownhostsfile"}


class TargetError(ValueError):
    """A target could not be selected or resolved; the message names the field or the choice."""


def declared_file(manifest: dict[str, Any]) -> str | None:
    return ((manifest.get("deploy") or {}).get("targets") or None) if isinstance(manifest.get("deploy"), dict) else None


def local_file(path: Path) -> Path:
    return path.with_name(path.name[: -len(".json")] + ".local.json") if path.name.endswith(".json") else path.with_name(path.name + ".local")


def _merge(base: Any, over: Any) -> Any:
    if isinstance(base, dict) and isinstance(over, dict):
        out = dict(base)
        for k, v in over.items():
            out[k] = _merge(base.get(k), v) if k in base else v
        return out
    return over


def _read(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise TargetError(f"{path.name}: not JSON ({e})") from e
    return data if isinstance(data, dict) else {}


def load(root: Path, manifest: dict[str, Any]) -> dict[str, Any] | None:
    """The declared targets merged with this machine's override, or None when none is declared."""
    rel = declared_file(manifest)
    if not rel:
        return None
    path = root / rel
    if not path.is_file():
        raise TargetError(f"deploy.targets: {rel} is not there")
    data = _read(path)
    local = local_file(path)
    if local.is_file():
        data = _merge(data, _read(local))
    return data


def default_layout() -> dict[str, str]:
    return {k: v for k, v in json.loads(DEFAULT_LAYOUT.read_text(encoding="utf-8")).items() if k in KINDS}


def pending_kinds() -> dict[str, str]:
    """The places declared ahead of the delivery that fills them, with why."""
    return dict(json.loads(DEFAULT_LAYOUT.read_text(encoding="utf-8")).get("pending") or {})


def compose_project(project: str, environment: str) -> str:
    """The docker compose project of one project's environment: its containers, networks and volumes
    are namespaced by it, so neither another project nor the other environment can collide."""
    return f"{project}-{environment}"


def _ports(data: dict[str, Any]) -> list[tuple[str, str, str, str, int]]:
    """(host, target, environment, service, port) for every declared host port."""
    out = []
    for name, t in (data.get("targets") or {}).items():
        if isinstance(t, dict):
            for env, services in (t.get("ports") or {}).items():
                for service, ports in (services or {}).items():
                    out += [(str(t.get("host") or name), name, env, service, int(p)) for p in ports or []]
    return out


def problems(root: Path, manifest: dict[str, Any]) -> list[str]:
    """What `validate` refuses in the declaration: its shape, a missing root, a secret value, a
    host-key option outside `hostKeys`, an unknown placeholder, a tracked override or key file."""
    from lib.schema_check import validate as schema_validate

    rel = declared_file(manifest)
    if not rel:
        return []
    out: list[str] = []
    path = root / rel
    try:
        data = load(root, manifest)
    except TargetError as e:
        return [str(e)]
    for f in (path, local_file(path)):
        if f.is_file() and _SECRET_TEXT.search(f.read_text(encoding="utf-8")):
            out.append(f"{f.relative_to(root).as_posix()}: holds private key material -- a target names an identity, never carries one")
    out += [f"{rel}: {e}" for e in schema_validate(data, json.loads(SCHEMA.read_text(encoding="utf-8")))]
    for name, t in (data.get("targets") or {}).items():
        if not isinstance(t, dict):
            continue
        where = f"{rel}: targets.{name}"
        if not t.get("pending"):
            for field in ("host", "user", "root"):
                if not t.get(field):
                    out.append(f"{where}.{field}: required (or declare the target `pending` with its reason)")
        for opt in (t.get("ssh") or {}).get("options") or []:
            if str(opt).split("=", 1)[0].lower() in _HOST_KEY_OPTIONS:
                out.append(f"{where}.ssh.options: {opt.split('=', 1)[0]} is `hostKeys`' to set (pinned | accept-new)")
        for tpl_name, tpl in {**default_layout(), **(t.get("layout") or {})}.items():
            bad = sorted(set(_PLACEHOLDER.findall(str(tpl))) - _ALLOWED)
            if bad:
                out.append(f"{where}.layout.{tpl_name}: unknown placeholder(s) {', '.join(bad)}")
                continue
            if t.get("root"):
                for env in environments(manifest):
                    try:
                        render(t, tpl_name, project="p", environment=env, service="s", container="s",
                               folder="f", infra_slug="i", manifest=manifest)
                    except TargetError as e:
                        out.append(f"{where}.layout.{tpl_name}: {e}")
                        break
        identity_ref = str((t.get("ssh") or {}).get("identity") or "")
        if identity_ref.startswith("file:") and _tracked(root, identity_ref[5:]):
            out.append(f"{where}.ssh.identity: {identity_ref[5:]} is tracked by git -- a key file is never committed")
        known = (t.get("ssh") or {}).get("knownHosts")
        if known and not (root / known).is_file():
            out.append(f"{where}.ssh.knownHosts: {known} is not there (pin the host key, verified out of band)")
    for _walk_key, _walk_path in _fields(data):
        if _SECRET_FIELD.match(_walk_key):
            out.append(f"{rel}: {_walk_path} names a secret -- secrets live in secret files or the store")
    if local_file(path).is_file() and _tracked(root, local_file(path).relative_to(root).as_posix()):
        out.append(f"{local_file(path).relative_to(root).as_posix()}: tracked by git -- the per-machine override is ignored by design")
    defaults = data.get("defaults") or {}
    envs = environments(manifest)
    from lib import catalogs

    runtimes = catalogs.ids("targetRuntimes", manifest)
    for env, name in defaults.items():
        if env not in envs:
            out.append(f"{rel}: defaults.{env}: '{env}' is not a declared environment ({', '.join(envs)})")
        if name not in (data.get("targets") or {}):
            out.append(f"{rel}: defaults.{env} names '{name}', which is not a target")
    for name, t in (data.get("targets") or {}).items():
        if isinstance(t, dict) and t.get("runtime") not in runtimes:
            out.append(f"{rel}: targets.{name}.runtime: '{t.get('runtime')}' is not a declared target runtime "
                       f"({', '.join(runtimes)}; a host adds one in catalogs.targetRuntimes)")
        for field in ("ports", "health"):
            for env in (t.get(field) or {}) if isinstance(t, dict) else {}:
                if env not in envs:
                    out.append(f"{rel}: targets.{name}.{field}.{env}: '{env}' is not a declared environment")
    seen: dict[tuple[str, int], str] = {}
    for host, name, env, service, port in _ports(data):
        here = f"targets.{name}.ports.{env}.{service}"
        if (host, port) in seen and seen[(host, port)] != here:
            out.append(f"{rel}: {here}: host port {port} on {host} is already {seen[(host, port)]}'s")
        seen.setdefault((host, port), here)
    return out


def notices(root: Path, manifest: dict[str, Any]) -> list[str]:
    """What `validate` prints but does not refuse: pending targets, unpinned host keys, trust on first
    use, and deploy.env server keys a declared target now overrides."""
    try:
        data = load(root, manifest)
    except TargetError:
        return []
    if data is None:
        return []
    out = []
    for name, t in (data.get("targets") or {}).items():
        if not isinstance(t, dict):
            continue
        if t.get("pending"):
            out.append(f"target {name}: pending -- {t['pending']}")
            continue
        ssh = t.get("ssh") or {}
        if ssh.get("hostKeys") == "accept-new":
            out.append(f"target {name}: hostKeys accept-new -- the first host key seen is trusted (declared)")
        elif not ssh.get("knownHosts"):
            out.append(f"target {name}: host key not pinned in the repository (strict against this machine's known_hosts)")
    return out


#: The deploy.env keys a target replaces; on a host without targets they are the deprecated home.
LEGACY_KEYS = ("DEPLOY_SERVER", "DEPLOY_SERVER_BASE", "DEPLOY_PATH", "DEPLOY_LAYOUT", "DEPLOY_PATH_MODE",
               "DEPLOY_SSH_CONFIG_FILE", "DEPLOY_SSH_IDENTITY_FILE", "DEPLOY_SSH_OPTIONS")


def legacy_files(secrets_root: Path, manifest: dict[str, Any]) -> dict[str, dict[str, str]]:
    """{file: {key: value}} of every env file that sets a deploy key a target owns."""
    from lib import envfile

    folders = {str(c.get("secretsModule") or m) for m, c in (manifest.get("modules") or {}).items() if isinstance(c, dict)}
    files = [secrets_root / "deploy.env", *(secrets_root / f / n for f in sorted(folders | {"infra"})
                                            for n in (".env.deploy", ".env.prod", ".env.dev"))]
    out = {}
    for f in files:
        hit = {k: v for k, v in envfile.parse(f).items() if k in LEGACY_KEYS}
        if hit:
            out[f.relative_to(secrets_root).as_posix()] = hit
    return out


def legacy_notices(secrets_root: Path, manifest: dict[str, Any]) -> list[str]:
    """Deprecation, by key NAME: a server still in deploy.env, or env-file deploy keys a declared
    target now overrides."""
    found = legacy_files(secrets_root, manifest)
    if not found:
        return []
    if declared_file(manifest):
        return [f"{f}: {', '.join(sorted(keys))} ignored -- the declared target answers them; remove them"
                for f, keys in found.items()]
    return [f"{f}: {', '.join(sorted(keys))} -- deprecated home of the deploy target (read until 2.0.0); "
            f"run `{identity.KIT_NAME} migrate --apply` to declare it in deploy.targets"
            for f, keys in found.items()]


def _fields(node: Any, path: str = "") -> list[tuple[str, str]]:
    out = []
    if isinstance(node, dict):
        for k, v in node.items():
            here = f"{path}.{k}" if path else str(k)
            parent = path.rsplit(".", 1)[-1] if path else ""
            if parent not in ("targets", "paths", "defaults"):  # names chosen by the host, not fields
                out.append((str(k), here))
            out += _fields(v, here)
    return out


def _tracked(root: Path, rel: str) -> bool:
    try:
        ran = subprocess.run(["git", "-C", str(root), "ls-files", "--error-unmatch", rel],
                             capture_output=True, text=True)
    except OSError:
        return False
    return ran.returncode == 0


def select(data: dict[str, Any], name: str = "", environment: str = "") -> tuple[str, dict[str, Any]]:
    """The target asked for (`--target`), else the environment's default, else the only one."""
    targets = data.get("targets") or {}
    if not environment:
        from lib import catalogs

        environment = catalogs.default_environment("deploy")
    chosen = name or (data.get("defaults") or {}).get(environment) or (next(iter(targets)) if len(targets) == 1 else "")
    if not chosen:
        raise TargetError(f"no target for '{environment}': pass --target <{'|'.join(targets) or 'name'}> "
                          f"or declare defaults.{environment}")
    if chosen not in targets:
        raise TargetError(f"no target '{chosen}' (declared: {', '.join(targets) or 'none'})")
    return chosen, targets[chosen]


def reachable(name: str, target: dict[str, Any]) -> dict[str, Any]:
    """The target, if a deploy may go to it; a pending one is refused with its reason."""
    if target.get("pending"):
        raise TargetError(f"target {name} is pending: {target['pending']}")
    for field in ("host", "user", "root"):
        if not target.get(field):
            raise TargetError(f"target {name}: {field} is not declared")
    return target


def server(name: str, target: dict[str, Any]) -> str:
    t = reachable(name, target)
    return f"{t['user']}@{t['host']}"


def render(target: dict[str, Any], kind: str, *, project: str, folder: str = "", container: str = "",
           environment: str = "prod", infra_slug: str = "", service: str = "",
           manifest: dict[str, Any] | None = None) -> str:
    """One remote path of a kind, from the target's layout over the kit's default -- normalised, and
    refused unless it lies under the project's own directory (and that under the target's root): one
    project can never write where another lives."""
    import posixpath

    if kind not in KINDS:
        raise TargetError(f"no layout kind '{kind}' (kinds: {', '.join(KINDS)})")
    known = environments(manifest)
    if environment not in known:
        raise TargetError(f"no environment '{environment}' (environments: {', '.join(known)})")
    layout = {**default_layout(), **(target.get("layout") or {})}
    root = str(target.get("root") or "")
    values = {"root": root.rstrip("/"), "project": project, "environment": environment,
              "service": service or container, "container": container or service, "folder": folder,
              "infraSlug": infra_slug or project}

    def one(name: str, seen: tuple[str, ...]) -> str:
        if name in seen:
            raise TargetError(f"layout.{name} refers to itself ({' -> '.join((*seen, name))})")

        def sub_one(m: re.Match[str]) -> str:
            key = m.group(1)
            return one(key[1:], (*seen, name)) if key.startswith("@") else values.get(key, m.group(0))
        return _PLACEHOLDER.sub(sub_one, layout[name])

    def normal(path: str) -> str:
        drive = re.match(r"^[A-Za-z]:", path)
        body = posixpath.normpath(path[2:] if drive else path)
        return (path[:2] if drive else "") + body

    project_dir = normal(one("project", ()))
    if not _under(project_dir, normal(root)) or project_dir == normal(root):
        raise TargetError(f"the project directory {project_dir} is not inside the target's root {root}")
    rendered = normal(one(kind, ()))
    if not _under(rendered, project_dir):
        raise TargetError(f"{kind} renders {rendered}, outside the project's directory {project_dir}")
    return rendered


def _under(path: str, base: str) -> bool:
    return path == base or path.startswith(base.rstrip("/") + "/")


def preflight(target: dict[str, Any], *, project: str, environment: str, repository: str,
              services: list[str]) -> str:
    """The script run on the server before any write of a deploy (`ssh <server> bash -s`): it claims
    the project's directory with an ownership marker, or refuses one another project owns, naming
    both; and refuses a declared host port a different compose project already publishes."""
    project_dir = render(target, "project", project=project, environment=environment)
    mine = compose_project(project, environment)
    want = json.dumps({"project": project, "repository": repository})
    q = lambda s: "'" + str(s).replace("'", "'\\''") + "'"
    lines = [
        "set -e",
        f"P={q(project_dir)}; M=\"$P/{MARKER}\"; WANT_PROJECT={q(project)}; WANT_REPO={q(repository)}",
        'if [ -e "$M" ]; then',
        '  have_project=$(sed -n \'s/.*"project": *"\\([^"]*\\)".*/\\1/p\' "$M")',
        '  have_repo=$(sed -n \'s/.*"repository": *"\\([^"]*\\)".*/\\1/p\' "$M")',
        '  if [ "$have_project" != "$WANT_PROJECT" ] || { [ -n "$have_repo" ] && [ -n "$WANT_REPO" ] && [ "$have_repo" != "$WANT_REPO" ]; }; then',
        '    echo "refused: $P belongs to project \'$have_project\' ($have_repo), not \'$WANT_PROJECT\' ($WANT_REPO)" >&2; exit 3',
        "  fi",
        "else",
        f'  mkdir -p "$P" && printf \'%s\\n\' {q(want)} > "$M"',
        "fi",
    ]
    ports = sorted({int(p) for svc, ps in ((target.get("ports") or {}).get(environment) or {}).items()
                    if not services or svc in services for p in ps or []})
    for port in ports:
        lines.append(f"owner=$(docker ps --filter publish={port} --format '{{{{.Label \"com.docker.compose.project\"}}}}' "
                     f"2>/dev/null | grep -v '^$' | grep -vx {q(mine)} | head -1 || true)")
        lines.append(f'if [ -n "$owner" ]; then echo "refused: host port {port} is published by compose project '
                     f'\'$owner\', not {mine}" >&2; exit 4; fi')
    return "\n".join(lines) + "\n"


def keep(target: dict[str, Any]) -> int:
    """How many releases (or versioned artifacts) a unit keeps; the prune limit verify holds."""
    return int(target.get("keep") or 5)


def declared_tree(target: dict[str, Any], *, project: str, services: list[str], environments: list[str],
                  infra_slug: str = "") -> dict[str, Any]:
    """The places a deploy may write for this project, per environment: the directories that must be
    there once an environment is deployed (`required`), and the subtrees whose inside is a driver's or
    the stack's own (`owned`: a unit, a workspace, the stack, infra)."""
    r = lambda kind, env, svc="": render(target, kind, project=project, environment=env, service=svc,
                                         container=svc, infra_slug=infra_slug)
    tree = {"project": r("project", "prod"), "environments": {}}
    for env in environments:
        units = {svc: r("unit", env, svc) for svc in services}
        owned = set(units.values()) | {r("stack", env), r("infra", env)}
        if env in _workspace_envs():
            owned |= {r("workspace", env, svc) for svc in services}
        tree["environments"][env] = {"dir": r("environment", env), "units": units, "owned": sorted(owned)}
    return tree


def verify_script(tree: dict[str, Any]) -> str:
    """A read-only listing of what is under the project's directory (`ssh <server> bash -s`): every
    path down to the owned subtrees (not into them), the marker, and per unit its release counts and
    whether `current` resolves. It writes nothing."""
    q = lambda s: "'" + str(s).replace("'", "'\\''") + "'"
    project_dir = tree["project"]
    owned = [o for env in tree["environments"].values() for o in env["owned"]]
    prune = " -o ".join(f"-path {q(o)}" for o in owned) or "-false"
    lines = [
        f"P={q(project_dir)}",
        'if [ ! -d "$P" ]; then echo "ABSENT"; exit 0; fi',
        f'if [ -f "$P/{MARKER}" ]; then echo "MARKER $(tr -d "\\n" < "$P/{MARKER}")"; else echo "MARKER-"; fi',
        f'find "$P" -mindepth 1 \\( {prune} \\) -print -prune -o -print 2>/dev/null | while IFS= read -r p; do',
        '  if [ -L "$p" ]; then t=l; elif [ -d "$p" ]; then t=d; else t=f; fi; echo "E $t $p"; done',
    ]
    for env in tree["environments"].values():
        for unit in env["units"].values():
            lines += [
                f"U={q(unit)}",
                'if [ -d "$U" ]; then',
                '  echo "R $U $(ls -1 "$U/releases" 2>/dev/null | wc -l | tr -d "[:space:]")"',
                '  echo "V $U $(ls -1 "$U"/versions/app-*.jar 2>/dev/null | wc -l | tr -d "[:space:]")"',
                '  if [ -L "$U/current" ]; then if [ -e "$U/current" ]; then echo "C $U ok"; else echo "C $U dangling"; fi; fi',
                "fi",
            ]
    return "\n".join(lines) + "\n"


def verify_report(tree: dict[str, Any], listing: str, *, project: str, repository: str,
                  keep_limit: int) -> list[str]:
    """Drift between the declared tree and what the listing says is there, one line each. Nothing
    is ever deleted: an undeclared path is reported, and stays."""
    lines = [ln for ln in listing.splitlines() if ln.strip()]
    project_dir = tree["project"]
    if lines[:1] == ["ABSENT"]:
        return [f"missing: {project_dir} (the project's directory -- nothing is deployed here)"]
    drift: list[str] = []
    marker = next((ln for ln in lines if ln.startswith("MARKER")), "MARKER-")
    if marker == "MARKER-":
        drift.append(f"marker absent: {project_dir}/{MARKER} (a deploy claims the directory first)")
    else:
        try:
            have = json.loads(marker[len("MARKER "):])
        except json.JSONDecodeError:
            have = {}
        if have.get("project") != project or (have.get("repository") and repository
                                              and have.get("repository") != repository):
            drift.append(f"marker names another project: {have.get('project')!r} ({have.get('repository') or '?'}), "
                         f"not {project!r} ({repository or '?'})")
    seen = {ln.split(" ", 2)[2]: ln.split(" ", 2)[1] for ln in lines if ln.startswith("E ")}
    allowed = {project_dir, f"{project_dir}/{MARKER}"}
    owned: list[str] = []
    for env in tree["environments"].values():
        owned += env["owned"]
        for path in [env["dir"], *env["units"].values(), *env["owned"]]:
            parts = path[len(project_dir):].strip("/").split("/")
            allowed |= {project_dir + "/" + "/".join(parts[:i]) for i in range(1, len(parts) + 1)}
        for svc, unit in env["units"].items():
            if unit not in seen:
                drift.append(f"missing: {unit} (service {svc})" + ("" if env["dir"] in seen else
                                                                    " -- the environment is not deployed"))
    for path in sorted(seen):
        if path not in allowed and not any(_under(path, o) for o in owned):
            drift.append(f"undeclared: {path} ({'directory' if seen[path] == 'd' else 'file'}; reported, never deleted)")
    for ln in lines:
        kind, _, rest = ln.partition(" ")
        if kind in ("R", "V"):
            unit, count = rest.rsplit(" ", 1)
            if int(count or 0) > keep_limit:
                what = "releases" if kind == "R" else "versioned artifacts (versions/app-*.jar)"
                drift.append(f"over the prune limit: {unit} keeps {count} {what}, the limit is {keep_limit}")
        if kind == "C" and rest.endswith(" dangling"):
            drift.append(f"current points at nothing: {rest.rsplit(' ', 1)[0]}/current")
    return drift


def repository_identity(root: Path) -> str:
    """This repository's identity for the ownership marker: its origin, as host/path (an https and an
    ssh spelling of one remote are one repository; credentials never enter it); "" without one."""
    try:
        ran = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"], capture_output=True, text=True)
    except OSError:
        return ""
    url = ran.stdout.strip() if ran.returncode == 0 else ""
    m = re.match(r"^(?:[a-z+]+://)?(?:[^@/]+@)?([^/:]+)[:/](.+?)(?:\.git)?/?$", url)
    return f"{m.group(1)}/{m.group(2)}".lower() if m else ""


def ssh_args(root: Path, name: str, target: dict[str, Any]) -> list[str]:
    """The openssh options (`-o`/`-F`, valid for ssh, scp and rsync -e) that reach the target."""
    t = reachable(name, target)
    ssh = t.get("ssh") or {}
    out = ["-o", f"Port={int(t.get('port') or 22)}"]
    if ssh.get("hostKeys") == "accept-new":
        out += ["-o", "StrictHostKeyChecking=accept-new"]
    else:
        out += ["-o", "StrictHostKeyChecking=yes"]
    if ssh.get("knownHosts"):
        out += ["-o", f"UserKnownHostsFile={(root / ssh['knownHosts']).as_posix()}"]
    ref = str(ssh.get("identity") or "agent")
    key = ""
    if ref.startswith("env:"):
        import os

        key = os.environ.get(ref[4:], "")
        if not key:
            raise TargetError(f"target {name}: ssh.identity {ref} -- ${ref[4:]} is not set")
    elif ref.startswith("file:"):
        key = (root / ref[5:]).as_posix()
    if key:
        out += ["-o", f"IdentityFile={key}", "-o", "IdentitiesOnly=yes"]
    if ssh.get("config"):
        out += ["-F", (root / ssh["config"]).as_posix()]
    for opt in ssh.get("options") or []:
        out += ["-o", str(opt)]
    return out


def identity_kind(target: dict[str, Any]) -> str:
    ref = str((target.get("ssh") or {}).get("identity") or "agent")
    return ref.split(":", 1)[0] if ":" in ref else ref


def verify(r: Any, data: dict[str, Any], argv: list[str]) -> int:
    """`targets --verify [--target <name>] [--env dev|prod]`: read the server, compare it with the
    declared tree, exit 1 on drift and 2 when nothing could be verified -- never a pass by default."""
    import os
    import shutil

    environments_ = ([argv[argv.index("--env") + 1]] if "--env" in argv and argv.index("--env") + 1 < len(argv)
                     else environments(r.manifest))
    try:
        name, t = select(data, identity.env("TARGET"), identity.env("ENVIRONMENT"))
        reachable(name, t)
    except TargetError as e:
        print(f"[verify] NOT VERIFIED: {e}")
        return 2
    project = r.project_slug()
    services = [container for _mid, _folder, container in r.module_deploy_units()]
    tree = declared_tree(t, project=project, services=services, environments=environments_,
                         infra_slug=r.infra_slug())
    ssh = shutil.which("ssh")
    if not ssh:
        print(f"[verify] NOT VERIFIED: target {name}: no ssh client on this machine")
        return 2
    ran = subprocess.run([ssh, *ssh_args(r.root, name, t), server(name, t), "bash", "-s"],
                         input=verify_script(tree), capture_output=True, text=True, env=dict(os.environ))
    if ran.returncode != 0:
        print(f"[verify] NOT VERIFIED: target {name} ({server(name, t)}) unreachable or refused "
              f"(ssh exit {ran.returncode}): {ran.stderr.strip()[:300]}")
        return 2
    drift = verify_report(tree, ran.stdout, project=project, repository=repository_identity(r.root),
                          keep_limit=keep(t))
    head = f"[verify] target {name}: {tree['project']} ({', '.join(environments_)})"
    if not drift:
        print(f"{head}: matches the declared tree")
        return 0
    print(f"{head}: {len(drift)} drift(s)")
    for line in drift:
        print(f"  {line}")
    return 1


def _environment(argv: list[str]) -> str:
    if "--env" in argv and argv.index("--env") + 1 < len(argv):
        return argv[argv.index("--env") + 1]
    if identity.env("ENVIRONMENT"):
        return identity.env("ENVIRONMENT")
    from lib import catalogs

    return catalogs.default_environment("deploy")


def health(data: dict[str, Any], argv: list[str], *, attempts: int = 0, pause: float = 0.0) -> int:
    """`targets --health [--target <name>] [--env dev|prod]`: every health URL the target declares for
    the environment answers below 400, retried while a release starts. Exit 1 naming each that does
    not; 2 when the target is pending; a target that declares none says so and passes nothing."""
    import time
    import urllib.error
    import urllib.request

    env = _environment(argv)
    try:
        name, t = select(data, identity.env("TARGET"), env)
        reachable(name, t)
    except TargetError as e:
        print(f"[health] NOT VERIFIED: {e}")
        return 2
    urls = ((t.get("health") or {}).get(env) or {})
    if not urls:
        print(f"[health] target {name} ({env}) declares no health endpoint -- nothing checked (targets.{name}.health.{env})")
        return 0
    attempts = attempts or int(os.environ.get(identity.env_name("HEALTH_ATTEMPTS")) or 12)
    pause = pause if attempts and pause else float(os.environ.get(identity.env_name("HEALTH_PAUSE")) or 5)
    failed = []
    for service, url in urls.items():
        last = ""
        for i in range(attempts):
            try:
                with urllib.request.urlopen(url, timeout=10) as resp:
                    if resp.status < 400:
                        print(f"[health] {service} {url} -> {resp.status}")
                        break
                    last = f"HTTP {resp.status}"
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}"
            except (urllib.error.URLError, OSError) as e:
                last = str(getattr(e, "reason", e))
            if i + 1 < attempts:
                time.sleep(pause)
        else:
            failed.append(f"{service} {url}: {last} after {attempts} attempt(s)")
    for f in failed:
        print(f"[health] FAILED {f}")
    return 1 if failed else 0


def main(argv: list[str]) -> int:
    from lib.resolution import Resolver

    try:
        r = Resolver()
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    try:
        data = load(r.root, r.manifest)
    except TargetError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if data is None:
        legacy = r.deploy_env_value("DEPLOY_SERVER") or r._any_folder("DEPLOY_SERVER")
        print(f"[targets] none declared (manifest `deploy.targets`)"
              + (f"; deploy.env names a server (deprecated: run `{identity.KIT_NAME} migrate --apply`)" if legacy else ""))
        return 0
    if "--verify" in argv:
        return verify(r, data, argv)
    if "--health" in argv:
        return health(data, argv)
    defaults = data.get("defaults") or {}
    for name, t in (data.get("targets") or {}).items():
        marks = [env for env, n in defaults.items() if n == name]
        head = f"{name}{' (default: ' + ', '.join(marks) + ')' if marks else ''}  runtime={t.get('runtime')}"
        if t.get("pending"):
            print(f"{head}  PENDING: {t['pending']}")
            continue
        ssh = t.get("ssh") or {}
        print(f"{head}  {t.get('user')}@{t.get('host')}:{t.get('port', 22)}  root={t.get('root')}  "
              f"identity={identity_kind(t)}  hostKeys={ssh.get('hostKeys', 'pinned')}"
              f"{'  knownHosts=' + ssh['knownHosts'] if ssh.get('knownHosts') else ''}")
        if "--plan" not in argv:
            continue
        pending = pending_kinds()
        mark = lambda kind: f"   (declared; pending: {pending[kind]})" if kind in pending else ""
        project = r.project_slug()
        units = r.module_deploy_units()
        print(f"  {render(t, 'project', project=project)}/            the project's own directory")
        print(f"    {MARKER}                ownership: {json.dumps({'project': project, 'repository': repository_identity(r.root)})}")
        for env in environments(r.manifest):
            env_dir = render(t, "environment", project=project, environment=env)
            print(f"    {env_dir}/     compose project {compose_project(project, env)}")
            print(f"      stack/                stack config: {render(t, 'stack', project=project, environment=env)}{mark('stack')}")
            for mid, folder, container in units:
                print(f"        env/{container}.env      {render(t, 'stackEnv', project=project, environment=env, service=container)}{mark('stackEnv')}")
            for mid, folder, container in units:
                ports = ((t.get("ports") or {}).get(env) or {}).get(container) or []
                print(f"      modules/{container}/      module {mid}: {render(t, 'unit', project=project, environment=env, service=container)}"
                      f"{'  ports ' + ','.join(map(str, ports)) if ports else ''}")
                for kind in ("logs", "releases", "current", "runtime"):
                    print(f"        {kind:<10}          {render(t, kind, project=project, environment=env, service=container)}{mark(kind)}")
                if env in _workspace_envs(r.manifest):
                    print(f"        workspace           {render(t, 'workspace', project=project, environment=env, service=container)}")
            print(f"      infra/                {render(t, 'infra', project=project, environment=env, infra_slug=r.infra_slug())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
