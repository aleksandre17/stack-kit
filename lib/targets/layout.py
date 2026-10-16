"""The ONE renderer of remote paths (ADR-001 amendments 9, 13).

Every path the kit touches on a server is rendered here, from the target's `layout` over the kit's
one default (config/deploy-layout.default.json), and refused unless it lies under the project's own
directory, itself strictly under the target's root. Nothing else composes a remote path: the
delivery engine, verify, init and migrate receive rendered paths (a test forbids building one from
a root or a project directory anywhere else).

    {root}/{project}/{environment}/{tier}/{service}     a unit (the default `unit`)
"""
from __future__ import annotations

import json
import posixpath
import re
from pathlib import Path
from typing import Any

KIT = Path(__file__).resolve().parents[2]
DEFAULT_LAYOUT = KIT / "config" / "deploy-layout.default.json"
#: The places a layout declares, in the order a tree prints them.
KINDS = ("project", "environment", "unit", "logs", "releases", "current", "runtime", "workspace", "stack",
         "stackCompose", "stackEnv", "stackState", "infra", "backups")
#: Kinds that are per service (they need {service} and {tier}).
UNIT_KINDS = ("unit", "logs", "releases", "current", "runtime", "workspace", "stackEnv")
PLACEHOLDER = re.compile(r"\{(@?[A-Za-z]+)\}")
VALUES = {"root", "project", "environment", "tier", "service", "infraSlug"}
ALLOWED = VALUES | {f"@{k}" for k in KINDS}
#: Where a project's ownership is written on the server, under its project directory.
MARKER = ".stack-kit-project"


class LayoutError(ValueError):
    """A path that cannot be rendered, or would land outside the project's directory."""


def _declaration() -> dict[str, Any]:
    return json.loads(DEFAULT_LAYOUT.read_text(encoding="utf-8"))


def default_layout() -> dict[str, str]:
    return {k: v for k, v in _declaration().items() if k in KINDS}


def declared_root(target: dict[str, Any]) -> str:
    """The target's root as declared -- for showing it; a path under it is only ever `render`ed."""
    return str(target.get("root") or "")


def unproven() -> str:
    """What the layout's delivery has not yet been proven against (the one `pending` it may carry)."""
    return str(_declaration().get("unproven") or "")


def under(path: str, base: str) -> bool:
    path, base = posixpath.normpath(path), posixpath.normpath(base)
    return path == base or path.startswith(base.rstrip("/") + "/")


def _normal(path: str) -> str:
    drive = re.match(r"^[A-Za-z]:", path)
    body = posixpath.normpath(path[2:] if drive else path)
    return (path[:2] if drive else "") + body


def render(target: dict[str, Any], kind: str, *, project: str, environment: str, service: str = "",
           tier: str = "", infra_slug: str = "", environments: list[str] | None = None) -> str:
    """One remote path of a kind -- normalised, and refused unless it lies under the project's own
    directory (and that strictly under the target's root): one project never writes where another
    lives, and nothing is ever rendered AT the root."""
    if kind not in KINDS:
        raise LayoutError(f"no layout kind '{kind}' (kinds: {', '.join(KINDS)})")
    if environments is not None and environment not in environments:
        raise LayoutError(f"no environment '{environment}' (environments: {', '.join(environments)})")
    if kind in UNIT_KINDS and not (service and tier):
        raise LayoutError(f"{kind} is a service's place: it needs the service and its tier")
    layout = {**default_layout(), **(target.get("layout") or {})}
    root = str(target.get("root") or "")
    if not root:
        raise LayoutError("the target declares no root")
    values = {"root": root.rstrip("/"), "project": project, "environment": environment, "tier": tier,
              "service": service, "infraSlug": infra_slug or project}

    def one(name: str, seen: tuple[str, ...]) -> str:
        if name in seen:
            raise LayoutError(f"layout.{name} refers to itself ({' -> '.join((*seen, name))})")

        def sub(m: re.Match[str]) -> str:
            key = m.group(1)
            if key.startswith("@"):
                return one(key[1:], (*seen, name))
            if key not in values:
                raise LayoutError(f"layout.{name}: unknown placeholder {{{key}}}")
            return values[key]
        return PLACEHOLDER.sub(sub, layout[name])

    project_dir = _normal(one("project", ()))
    if not under(project_dir, _normal(root)) or project_dir == _normal(root):
        raise LayoutError(f"the project directory {project_dir} is not strictly inside the target's root {root}")
    rendered = _normal(one(kind, ()))
    if not under(rendered, project_dir):
        raise LayoutError(f"{kind} renders {rendered}, outside the project's directory {project_dir}")
    return rendered


def problems(target: dict[str, Any], environments: list[str]) -> list[str]:
    """Each template's placeholders known, and every kind renderable for every environment."""
    out = []
    for name, tpl in {**default_layout(), **(target.get("layout") or {})}.items():
        bad = sorted(set(PLACEHOLDER.findall(str(tpl))) - ALLOWED)
        if bad:
            out.append(f"layout.{name}: unknown placeholder(s) {', '.join(bad)}")
            continue
        if target.get("root"):
            for env in environments:
                try:
                    render(target, name, project="p", environment=env, service="s", tier="t", infra_slug="i")
                except LayoutError as e:
                    out.append(f"layout.{name}: {e}")
                    break
    return out


def isolation_problems(target: dict[str, Any], environments: list[str]) -> list[str]:
    """Each environment its own tree, stack and state: a layout that renders two environments into one
    place (or one inside the other) would let a dev deploy overwrite production."""
    out = []
    for i, a in enumerate(environments):
        for b in environments[i + 1:]:
            for kind in ("environment", "stack", "stackCompose", "stackState", "infra", "backups"):
                try:
                    pa = render(target, kind, project="p", environment=a, service="s", tier="t")
                    pb = render(target, kind, project="p", environment=b, service="s", tier="t")
                except LayoutError:
                    continue
                if under(pa, pb) or under(pb, pa):
                    out.append(f"layout.{kind}: {a} and {b} share {pa if under(pb, pa) else pb} -- each environment needs its own")
    return out


class Places:
    """The rendered places of one project's environment on one target: what every remote step gets
    instead of a root. `of(kind, service)` answers a service's place; `confine` is the environment's
    directory, the boundary every remove is held to."""

    def __init__(self, target: dict[str, Any], *, project: str, environment: str,
                 environments: list[str] | None = None) -> None:
        self.target, self.project, self.environment = target, project, environment
        self.environments = environments
        self.project_dir = self.of("project")
        self.environment_dir = self.of("environment")

    def of(self, kind: str, service: Any = None, *, infra_slug: str = "") -> str:
        sid = getattr(service, "id", service) or ""
        tier = getattr(service, "tier", "") if service is not None else ""
        return render(self.target, kind, project=self.project, environment=self.environment, service=str(sid),
                      tier=str(tier), infra_slug=infra_slug, environments=self.environments)

    def unit(self, service: Any) -> dict[str, str]:
        return {k: self.of(k, service) for k in UNIT_KINDS}

    def marker(self) -> str:
        return posixpath.join(self.project_dir, MARKER)

    def held(self, path: str) -> bool:
        """Whether a path is strictly inside this project's environment (where removes may happen)."""
        return under(path, self.environment_dir) and posixpath.normpath(path) != self.environment_dir


def render_legacy(target: dict[str, Any], template: str, *, project: str, service: str = "", tier: str = "") -> str:
    """A path of a tree the platform laid out before this layout (a target's `legacyLayout`), for
    `layout migrate` to move from. It must lie at least two levels under the root: the root's own
    children (backend/, frontend/, infra/, backups/ ...) are shared between projects and are never
    moved, removed or claimed -- only a path the host declares as its own, inside one of them."""
    root = _normal(str(target.get("root") or ""))
    values = {"root": root, "project": project, "service": service, "tier": tier}

    def sub(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in values:
            raise LayoutError(f"legacyLayout: unknown placeholder {{{key}}} in {template}")
        return values[key]
    path = _normal(PLACEHOLDER.sub(sub, template))
    if not under(path, root) or path == root:
        raise LayoutError(f"legacyLayout: {path} is not inside the target's root {root}")
    depth = len(path[len(root):].strip("/").split("/"))
    if depth < 2:
        raise LayoutError(f"legacyLayout: {path} is a direct child of the shared root -- it holds other projects' "
                          f"trees; declare this project's own path inside it")
    return path
