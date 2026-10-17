"""Extension points: every place a host extends the kit, one grammar (ADR-001 amendments 15, 16.4;
config/extension-points.json is in the shape agent-kit shares -- config/extension-points.schema.json,
vendored byte for byte from agent-kit, its origin and sha256 in config/vendored.json).

`required_by` names the profile that requires a point answered: `init` is the base every host has
(init lays the point down, and every declared profile requires it), any other value only that
profile (`extend.profile`). A point `<id>-entry` is the companion of `<id>`: made with it, under the
same name (an infra service's manifest entry, a driver's registry entry).

A host file -- or an entry inside one (`file#/json/pointer`) -- is created from its template on
demand, never as a tree of empty files; the answers only the host can give are <<pending: ...>>
markers that `extend --list` and `validate` show; when a template changes, `extend --upgrade`
merges it 3-way (the base it was made from, the new template, the host's file) and reports a
conflict instead of overwriting. The kit copy is never edited: what the kit serves is its base
composed with the host's extensions as each point's `merges_into` says. `init` is `extend` of every
point required by `init`; `init --plan` is `extend module` (the draft from the tree).
"""
from __future__ import annotations

import fnmatch
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lib.identity import MANIFEST_FILENAME

KIT = Path(__file__).resolve().parents[1]
REGISTRY = KIT / "config" / "extension-points.json"
LOCK = "ops/stack-kit/extensions.lock.json"
PENDING = re.compile(r"<<pending:\s*([^>]*)>>")
_FIELD = re.compile(r"\{([A-Za-z0-9_.]+)\|([^}]*)\}")
#: Where a tier's files go, rendered from the host (`<tier:T>` its module's path, `<secrets:T>` that
#: module's secrets folder, `<up:T>` the way back from it to the root): the first module whose role
#: lives in tier T, else the layout profile's `tiers.T` (`{project}` filled), else `apps/T`.
_TIER = re.compile(r"<(tier|secrets|up):([a-z0-9][a-z0-9-]*)>")
#: The base profile: what init lays down, required by every profile.
INIT = "init"
#: A point `<id>` + one of these suffixes is made with `<id>`, under the same name (a driver brings its
#: registry entry and the lifecycle scripts the entry's `commands` name).
COMPANIONS = ("-entry", "-build", "-test")
COMPANION = COMPANIONS[0]


class ExtendError(ValueError):
    """An extension that cannot be made honestly, named."""


@dataclass
class Place:
    point: dict[str, Any]
    name: str
    file: Path
    pointer: list[str] | None      # None: the whole file is the extension

    @property
    def rel(self) -> str:
        return self.file.as_posix()


def points() -> dict[str, dict[str, Any]]:
    return {p["id"]: p for p in json.loads(REGISTRY.read_text(encoding="utf-8"))["points"]}


def _tier_module(manifest: dict[str, Any], tier: str) -> tuple[str, str] | None:
    """(path, secrets folder) of the first module whose role lives in `tier`."""
    from lib import catalogs

    for mid, cfg in (manifest.get("modules") or {}).items():
        if not isinstance(cfg, dict) or not cfg.get("path"):
            continue
        entry = catalogs.entry("roles", str(cfg.get("role") or ""), manifest) or {}
        if entry.get("tier") == tier:
            return str(cfg["path"]).replace("\\", "/").strip("/"), str(cfg.get("secretsModule") or mid)
    return None


def _profile_tier(manifest: dict[str, Any], tier: str) -> str:
    profile = str((manifest.get("layout") or {}).get("profile") or "")
    f = KIT / "config" / "layout-profiles" / f"{profile}.json"
    if not profile or not f.is_file():
        return ""
    tpl = str((json.loads(f.read_text(encoding="utf-8")).get("tiers") or {}).get(tier) or "")
    return tpl.replace("{project}", str(manifest.get("project") or "app")).strip("/")


def placed(text: str, manifest: dict[str, Any]) -> str:
    """`text` with each tier token rendered from the host's modules, its layout profile, its tiers."""
    def one(m: re.Match[str]) -> str:
        kind, tier = m.group(1), m.group(2)
        mod = _tier_module(manifest, tier)
        path = mod[0] if mod else (_profile_tier(manifest, tier) or f"apps/{tier}")
        if kind == "tier":
            return path
        if kind == "secrets":
            return mod[1] if mod else tier
        return "/".join([".."] * len([p for p in path.split("/") if p and p != "."])) or "."
    return _TIER.sub(one, text)


def _host_path(point: dict[str, Any], manifest: dict[str, Any], name: str) -> tuple[str, list[str] | None]:
    def field(m: re.Match[str]) -> str:
        cur: Any = manifest
        for part in m.group(1).split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
        return str(cur) if isinstance(cur, str) and cur else m.group(2)
    path = placed(_FIELD.sub(field, point["host_path"]), manifest).replace("<name>", name)
    if "#/" in path:
        f, ptr = path.split("#/", 1)
        return f, [p.replace("~1", "/").replace("~0", "~") for p in ptr.split("/")]
    return path, None


def place(point: dict[str, Any], manifest: dict[str, Any], name: str = "") -> Place:
    if point["cardinality"] == "many" and not name:
        raise ExtendError(f"{point['id']} is a `many` point: name the one to make (`extend {point['id']} <name>`)")
    f, ptr = _host_path(point, manifest, name)
    return Place(point, name, Path(f), ptr)


def unoccupied(text: str, manifest: dict[str, Any]) -> list[str]:
    """The tiers a text places files in (`<tier:T>`, `<secrets:T>`, `<up:T>`) that no module lives in --
    where a file would be laid for a module the host does not have (found adopting a foreign project:
    `apps/backend/` was scaffolded for a project with no backend)."""
    return sorted({m.group(2) for m in _TIER.finditer(text) if _tier_module(manifest, m.group(2)) is None})


def catalog_for_host(raw: str, manifest: dict[str, Any]) -> str:
    """The local stack's catalog, made for THIS host's modules: a target for a tier no module lives in is
    left out; a tier's hand-written service templates give way to the module's own service, rendered from
    its manifest and its driver (`manifestModule`: its path, its secrets, its port, its recipe) -- one
    file per profile, no overlays a template needed; the embedded worker is off unless the host declares
    one (`modules.<api>.compose.embeddedWorker`)."""
    doc = json.loads(raw)
    targets = {}
    for key, spec in (doc.get("targets") or {}).items():
        if unoccupied(key, manifest):
            continue
        tiers = [m.group(2) for m in _TIER.finditer(key) if m.group(1) == "tier"]
        if tiers and (spec.get("services") or spec.get("extraServices")) and not spec.get("manifestModule"):
            if "override" in key:
                continue  # an overlay of a hand-written template: the module's own service needs none
            mod = _tier_module(manifest, tiers[0])
            mid = next((m for m, c in (manifest.get("modules") or {}).items() if isinstance(c, dict)
                        and str(c.get("path") or "").replace("\\", "/").strip("/") == (mod[0] if mod else None)), None)
            if not mid:
                continue
            spec = {k: v for k, v in {"comment": spec.get("comment"), "manifestModule": mid,
                                      "manifestProfile": "prod" if key.endswith(".prod.yml") else "dev",
                                      "networks": spec.get("networks") or "net_bridge"}.items() if v}
        targets[key] = spec
    doc["targets"] = targets
    doc["features"] = {**(doc.get("features") or {}), "worker": False}
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def template_text(point: dict[str, Any], name: str, manifest: dict[str, Any] | None = None) -> str:
    rel = point["template"].replace("<name>", name)
    path = KIT / rel
    if not path.is_file():
        raise ExtendError(f"{point['id']}: no template {rel} -- the kit offers "
                          + ", ".join(sorted(p.stem for p in path.parent.glob("*" + path.suffix))) if path.parent.is_dir()
                          else f"{point['id']}: no template {rel}")
    text = path.read_text(encoding="utf-8").replace("<name>", name)
    if manifest is not None and point["id"] == "compose-catalog":
        text = catalog_for_host(text, manifest)
    return text if manifest is None else rendered_for(text, manifest)


def rendered_for(text: str, manifest: dict[str, Any]) -> str:
    """A template's text placed for this host: its tier tokens and, where it has them, its manifest fields."""
    if not _TIER.search(text):
        return text

    def field(m: re.Match[str]) -> str:
        cur: Any = manifest
        for part in m.group(1).split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
        return str(cur) if isinstance(cur, str) and cur else m.group(2)
    return placed(_FIELD.sub(field, text), manifest)


def _get(doc: Any, ptr: list[str], name: str) -> Any:
    cur = doc
    for i, part in enumerate(ptr):
        if part == "-":
            if not isinstance(cur, list):
                return None
            return next((x for x in cur if x == name or (isinstance(x, dict) and x.get("id", x.get("key")) == name)), None)
        cur = cur.get(part) if isinstance(cur, dict) else None
        if cur is None:
            return None
    return cur


def _set(doc: dict[str, Any], ptr: list[str], value: Any) -> None:
    cur: Any = doc
    for i, part in enumerate(ptr[:-1]):
        nxt = ptr[i + 1]
        if part not in cur or cur[part] is None:
            cur[part] = [] if nxt == "-" else {}
        cur = cur[part]
    if ptr[-1] == "-":
        cur.append(value)
    else:
        cur[ptr[-1]] = value


def _load(root: Path, rel: Path) -> dict[str, Any]:
    p = root / rel
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def existing(root: Path, p: Place) -> Any:
    if p.pointer is None:
        f = root / p.file
        return f.read_text(encoding="utf-8") if f.is_file() else None
    return _get(_load(root, p.file), p.pointer, p.name)


def status_of(value: Any) -> str:
    if value is None:
        return "unused"
    return "drafted" if PENDING.search(value if isinstance(value, str) else json.dumps(value)) else "answered"


def pending_in(value: Any) -> list[str]:
    return PENDING.findall(value if isinstance(value, str) else json.dumps(value)) if value is not None else []


def make(root: Path, manifest: dict[str, Any], point_id: str, name: str = "", *, plan: bool = False) -> list[str]:
    """The extension (and its companions) from the template -- idempotent, never overwriting."""
    pts = points()
    if point_id not in pts:
        raise ExtendError(f"no extension point '{point_id}' (extend --list)")
    point = pts[point_id]
    p = place(point, manifest, name)
    said: list[str] = []
    if existing(root, p) is not None:
        said.append(f"{point_id}{' ' + name if name else ''}: already there ({p.rel}{'#/' + '/'.join(p.pointer) if p.pointer else ''}) -- not overwritten")
    else:
        text = template_text(point, name, manifest)
        if p.pointer is None:
            said.append(f"{'plan: ' if plan else ''}create {p.rel} from {point['template'].replace('<name>', name)}")
            if not plan:
                f = root / p.file
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(text, encoding="utf-8", newline="\n")
                _lock(root, p.rel, point_id, name, text, point["template"].replace("<name>", name))
                for comp in _companion_files(point, name):
                    cf = f.parent.parent / comp if point_id == "infra-service" else f.parent / comp
                    if not cf.exists():
                        cf.parent.mkdir(parents=True, exist_ok=True)
                        body = (KIT / "scaffold/ops/compose/infra" / comp).read_text(encoding="utf-8")
                        cf.write_text(body, encoding="utf-8", newline="\n")
                        rel = cf.relative_to(root).as_posix()
                        _lock(root, rel, point_id, name, body, f"scaffold/ops/compose/infra/{comp}")
                        said.append(f"create {rel}")
        else:
            value = json.loads(text)
            said.append(f"{'plan: ' if plan else ''}add {p.rel}#/{'/'.join(p.pointer)}" + (f" ({name})" if name else ""))
            if not plan:
                doc = _load(root, p.file)
                _set(doc, p.pointer, value)
                (root / p.file).parent.mkdir(parents=True, exist_ok=True)
                (root / p.file).write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    for suffix in COMPANIONS:
        if point_id + suffix in points():
            said += make(root, manifest, point_id + suffix, name, plan=plan)
    return said


def _companion_files(point: dict[str, Any], name: str) -> list[str]:
    """Files a named infra template brings with it (its catalog entry's `files`)."""
    if point["id"] != "infra-service":
        return []
    cat = json.loads((KIT / "compose" / "infra-catalog.json").read_text(encoding="utf-8"))
    return list(((cat.get("modules") or {}).get(name) or {}).get("files") or [])


def _lock(root: Path, rel: str, point_id: str, name: str, base: str, template: str) -> None:
    """What a file was made from (its template, and the text it was then): the base of a later 3-way merge."""
    f = root / LOCK
    data = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {"schema": 1, "files": {}}
    data["files"][rel] = {"point": point_id, "name": name, "template": template, "base": base}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def merge3(host: str, base: str, new: str) -> tuple[str, int]:
    """(merged, conflicts) of `git merge-file` -- the host's changes and the template's, together."""
    with tempfile.TemporaryDirectory() as d:
        paths = []
        for n, text in (("host", host), ("base", base), ("new", new)):
            p = Path(d) / n
            p.write_text(text, encoding="utf-8", newline="\n")
            paths.append(str(p))
        ran = subprocess.run(["git", "merge-file", "-p", "-L", "yours", "-L", "base", "-L", "kit", *paths],
                             capture_output=True, text=True, encoding="utf-8")
        if ran.returncode < 0:
            raise ExtendError(f"git merge-file failed: {ran.stderr.strip()}")
        return ran.stdout, ran.returncode


def upgrade(root: Path, *, plan: bool = False) -> list[str]:
    """Every file made from a template that has changed since: merged 3-way, a conflict reported and
    the host's file left as it is."""
    f = root / LOCK
    if not f.is_file():
        return ["nothing was made from a template here (no extensions lock)"]
    data = json.loads(f.read_text(encoding="utf-8"))
    pts = points()
    manifest = _load(root, Path(MANIFEST_FILENAME))
    said = []
    for rel, entry in sorted(data["files"].items()):
        point = pts.get(entry["point"])
        target = root / rel
        if point is None or not target.is_file():
            said.append(f"{rel}: {'its point is gone' if point is None else 'removed by the host'} -- left alone")
            continue
        source = KIT / entry["template"]
        if not source.is_file():
            said.append(f"{rel}: the kit no longer has its template {entry['template']} -- left alone")
            continue
        new = rendered_for(source.read_text(encoding="utf-8").replace("<name>", entry.get("name", "")), manifest)
        if new == entry["base"]:
            continue
        host = target.read_text(encoding="utf-8")
        merged, conflicts = merge3(host, entry["base"], new)
        if conflicts:
            said.append(f"{rel}: CONFLICT ({conflicts}) between your changes and the kit's new template -- left as it is; "
                        f"merge by hand (the kit's: {point['template'].replace('<name>', entry.get('name', ''))})")
            continue
        said.append(f"{'plan: ' if plan else ''}merge the kit's new template into {rel}")
        if not plan:
            target.write_text(merged, encoding="utf-8", newline="\n")
            entry["base"] = new
    if not plan:
        f.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return said or ["every extension is on its template's current version"]


def listing(root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Each point with its instances: (point, name, place, status, pending questions)."""
    out = []
    for point in points().values():
        names = [""] if point["cardinality"] == "one" else _names(root, manifest, point)
        for name in names or [None]:
            if name is None:
                out.append({"point": point, "name": "", "place": None, "status": "unused", "pending": []})
                continue
            p = place(point, manifest, name)
            value = existing(root, p)
            out.append({"point": point, "name": name, "place": p, "status": status_of(value), "pending": pending_in(value)})
    return out


def _names(root: Path, manifest: dict[str, Any], point: dict[str, Any]) -> list[str]:
    """The instances of a `many` point the host has."""
    probe = place(point, manifest, "\0")
    if probe.pointer is None:
        pattern = probe.rel.replace("\0", "*")
        found = sorted(root.glob(pattern))
        rx = re.compile("^" + re.escape(probe.rel).replace("\\x00", "\0").replace("\0", "(.+)") + "$")
        return [m.group(1) for f in found if (m := rx.match(f.relative_to(root).as_posix()))]
    doc = _load(root, probe.file)
    ptr = probe.pointer
    i = ptr.index("\0") if "\0" in ptr else ptr.index("-")
    parent = _get(doc, ptr[:i], "") if i else doc
    if ptr[i] == "-":
        return [str(x if isinstance(x, str) else x.get("id", x.get("key"))) for x in parent or []
                if isinstance(x, (str, dict))]
    return sorted(parent) if isinstance(parent, dict) else []


def undeclared(root: Path, manifest: dict[str, Any]) -> list[str]:
    """Files in a directory a point owns that no point declares (a host extension reached by no point)."""
    pts = list(points().values())
    owned: set[str] = set()
    patterns: list[str] = []
    for point in pts:
        p = place(point, manifest, "*" if point["cardinality"] == "many" else "")
        if p.pointer is None:
            patterns.append(p.rel)
            if point["cardinality"] == "many":
                owned.add(p.rel.split("*")[0].rstrip("/"))
        patterns.append(p.rel)
    out = []
    for d in sorted(owned):
        base = root / d
        for f in sorted(base.rglob("*")) if base.is_dir() else []:
            rel = f.relative_to(root).as_posix()
            if f.is_file() and not any(fnmatch.fnmatch(rel, pat) for pat in patterns):
                extra = _companions_of(rel)
                if not extra:
                    out.append(rel)
    # An ignored file (an env file `extend env` made, a local overlay) is machine state, never a host
    # extension: only what the repository carries is held to a declared point.
    return [rel for rel in out if rel not in _ignored(root, out)]


def _ignored(root: Path, rels: list[str]) -> set[str]:
    if not rels:
        return set()
    import subprocess

    # Bytes, not text: text mode on Windows turns each "\n" into "\r\n", and git then reads every path
    # but the last with a trailing "\r" -- a path that is never ignored.
    ran = subprocess.run(["git", "-C", str(root), "check-ignore", "--stdin"], input="\n".join(rels).encode("utf-8"),
                         capture_output=True)
    return {line.strip() for line in ran.stdout.decode("utf-8", "replace").splitlines() if line.strip()}


def _companions_of(rel: str) -> bool:
    cat = json.loads((KIT / "compose" / "infra-catalog.json").read_text(encoding="utf-8"))
    files = {f for m in (cat.get("modules") or {}).values() for f in m.get("files") or []}
    return any(rel.endswith("/" + f) for f in files)


def copy_placed(kit_rel: str, root: str | Path, rel: str) -> None:
    """A kit file laid into the host, its tier tokens placed for it (init's minimal compose catalog)."""
    root = Path(root)
    target = root / rel
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    text = rendered_for((KIT / kit_rel).read_text(encoding="utf-8"), _load(root, Path(MANIFEST_FILENAME)))
    target.write_text(text, encoding="utf-8", newline="\n")


def init(root: Path, *, plan: bool = False) -> list[str]:
    """What init lays down: every point required by `init`, then each infra service the manifest selects."""
    said = []
    for point in points().values():
        if point.get("required_by") == INIT:
            manifest = _load(root, Path(MANIFEST_FILENAME))
            empty = unoccupied(point["host_path"], manifest)
            if empty:
                said.append(f"{point['id']}: skipped -- no module lives in tier {', '.join(empty)}")
                continue
            said += make(root, manifest, point["id"], plan=plan)
    manifest = _load(root, Path(MANIFEST_FILENAME))
    for svc in ((manifest.get("stack") or {}).get("infra") or {}).get("services") or []:
        p = place(points()["infra-service"], manifest, svc)
        if existing(root, p) is None:
            said += make(root, manifest, "infra-service", svc, plan=plan)
    return said


def problems(root: Path, manifest: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(errors, notices) for validate: pending answers (an error only where the manifest's profile
    requires the point), undeclared extension files."""
    profile = str((manifest.get("extend") or {}).get("profile") or "")
    errors, notices = [], []
    for row in listing(root, manifest):
        point = row["point"]
        required = bool(profile) and point.get("required_by") in (INIT, profile)
        if row["status"] == "drafted":
            line = f"extension {point['id']}{' ' + row['name'] if row['name'] else ''}: pending -- " + "; ".join(row["pending"])
            (errors if required else notices).append(line)
        elif row["status"] == "unused" and required and point["cardinality"] == "one":
            errors.append(f"extension {point['id']}: required by profile {profile}, not made (`extend {point['id']}`)")
    notices += [f"extension: {rel} is in a place an extension point owns, but no point declares it" for rel in undeclared(root, manifest)]
    return errors, notices
