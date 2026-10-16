"""One home per fact, held deny-by-default (ADR-001 amendment 13): no generic script names a tool or
a driver; each declaration file is read by its one module; a former home's key is spelled only by
the module that names it and the one that migrates it; no remote path is composed from a root or a
project directory outside the layout; no import cycle. Each rule carries a sensor test that sees the
violation it forbids, so an empty result is a finding, not a blind spot."""
from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

from conftest import PKG

#: Where a tool may be named: a driver's own directory (the drivers are where tools live), the
#: tests, a tool's adapter (named for it), and the scaffold (a sample host).
TOOL_HOMES = ("drivers/", "tests/", "adapters/", "scaffold/")
TOOLS = re.compile(r"\b(gradlew?|jar|java|node|npm|pnpm|npx|yarn|dotnet|bootjar|bootrun|mvn|maven|temurin|csproj)\b",
                   re.IGNORECASE)
#: Generic code that still names a tool, each with why -- a ratchet: an entry whose file no longer
#: names one fails, so the list only shrinks.
OWED = {
    "lib/vscode_gen.py": "VS Code debugger types per toolchain: its builders move into each driver's vscode.launch data",
    "compose/manifest_compose.py": "local compose-gen's ops.modules registry rows (a driver's compose.opsModules)",
    "compose/sync_ops_modules.py": "local compose-gen's shared-submodule row",
}


def _tracked(*globs: str) -> list[str]:
    out = subprocess.run(["git", "-C", str(PKG), "ls-files", "-co", "--exclude-standard", *globs],
                         capture_output=True, text=True).stdout.splitlines()
    return [r for r in out if (PKG / r).is_file()]


def _code(rel: str) -> str:
    return (PKG / rel).read_text(encoding="utf-8-sig", errors="replace")


def tool_hits(text: str) -> list[str]:
    return [m.group(0) for m in TOOLS.finditer(text)]


def test_no_generic_script_names_a_tool():
    offenders, cured = [], []
    for rel in _tracked("*.py", "*.ps1", "*.sh"):
        if rel.startswith(TOOL_HOMES):
            continue
        hits = tool_hits(_code(rel))
        if hits and rel not in OWED:
            offenders.append(f"{rel}: {sorted(set(hits))}")
        if not hits and rel in OWED:
            cured.append(rel)
    assert not offenders, "a generic script names a tool:\n  " + "\n  ".join(offenders)
    assert not cured, f"cured -- take them off OWED: {cured}"


def test_the_tool_sensor_sees_a_tool():
    assert tool_hits("run ./gradlew bootJar") and tool_hits("dotnet publish") and tool_hits("npm ci")
    assert not tool_hits("the node-terminal launch") or tool_hits("node")  # a word boundary is a hit by design
    assert not tool_hits("a nodes list")


#: Each declaration file and the one module that reads it.
DECLARATIONS = {
    "deploy-layout.default.json": {"lib/targets/layout.py"},
    "deploy-targets.schema.json": {"lib/targets/declaration.py"},
    "delivery.json": {"lib/delivery/model.py"},
    "runtimes.json": {"lib/modules.py"},
    "registry.json": {"lib/modules.py", "lib/draft.py", "lib/validate_manifest.py"},
}


def readers(name: str) -> set[str]:
    """The scripts that build the file's path: its name as a quoted path segment (a mention in prose is not a read)."""
    seg = re.compile(r"[\"']" + re.escape(name) + r"[\"']")
    return {rel for rel in _tracked("*.py", "*.ps1", "*.sh")
            if not rel.startswith(("tests/", "drivers/")) and seg.search(_code(rel))}


def test_each_declaration_file_is_read_by_its_one_home():
    wrong = {name: sorted(readers(name) - homes) for name, homes in DECLARATIONS.items()}
    wrong = {k: v for k, v in wrong.items() if v}
    assert not wrong, f"a declaration file read outside its home: {wrong}"
    catalog_readers = {rel for rel in _tracked("*.py", "*.ps1", "*.sh")
                       if not rel.startswith("tests/") and re.search(r"[\"']config[/\\]catalogs|CATALOGS\s*/", _code(rel))}
    assert catalog_readers <= {"lib/catalogs.py"}, catalog_readers


#: The former homes' keys (lib/legacy.py) -- spelled by the module that names them, the one that
#: carries them, and the changelog/ADR history; read by nothing.
LEGACY_KEYS = re.compile(r"\b(DEPLOY_(?:SERVER|SERVER_BASE|PATH|LAYOUT|PATH_MODE|PROJECT|HOST_PORT|SSH_\w+)|"
                         r"COMPOSE_PROJECT_NAME|COMPOSE_[A-Z]+_SERVICE|DOCKER_NETWORK|INFRA_SLUG)\b")
LEGACY_HOMES = {"lib/legacy.py", "lib/migrate_legacy.py"}


def test_a_former_homes_key_is_spelled_only_where_it_is_named_or_carried():
    found = sorted(f"{rel}: {sorted(set(LEGACY_KEYS.findall(_code(rel))))}" for rel in _tracked("*.py", "*.ps1", "*.sh", "*.json")
                   if not rel.startswith("tests/") and rel not in LEGACY_HOMES and LEGACY_KEYS.search(_code(rel)))
    assert not found, "a former home's key outside lib/legacy.py and lib/migrate_legacy.py:\n  " + "\n  ".join(found)
    files = sorted(rel for rel in _tracked("*.py", "*.ps1", "*.sh") if not rel.startswith("tests/")
                   and rel not in LEGACY_HOMES | {"lib/envfile.py", "lib/config_keys.py"} and re.search(r"[\"'](?:[\w./-]*/)?(?:deploy\.env|\.env\.deploy)[\"']", _code(rel)))
    assert not files, f"a former env file read outside its homes: {files}"


#: A remote path composed from a root or a project directory, outside the one renderer.
COMPOSED = re.compile(r"""\[["']root["']\]|\.get\(["']root["']\)|join\(\s*[\w.]*\b(?:root|project_dir|environment_dir)\b\s*,|"""
                      r"""f["'][^"'\n]*\{[\w.]*\b(?:root|project_dir|environment_dir)\b\}/""")
COMPOSE_HOMES = {"lib/targets/layout.py", "lib/targets/declaration.py", "lib/migrate_legacy.py"}


def composed(text: str) -> list[str]:
    return [m.group(0) for m in COMPOSED.finditer(text)]


def test_no_remote_path_is_composed_outside_the_layout():
    found = []
    for rel in _tracked("*.py"):
        if not rel.startswith(("lib/delivery/", "lib/targets/", "lib/cli/")) or rel in COMPOSE_HOMES:
            continue
        hits = composed(_code(rel))
        if hits:
            found.append(f"{rel}: {hits}")
    assert not found, "a remote path composed from a root or project directory:\n  " + "\n  ".join(found)


def test_the_composition_sensor_sees_a_composed_path():
    assert composed('posixpath.join(project_dir, "x")') and composed('f"{t.root}/x"') and composed('target["root"]')
    assert composed('posixpath.join(ctx.places.environment_dir, "x")')
    assert not composed('ctx.places.of("unit", s)') and not composed("posixpath.join(unit['releases'], rid)")


def _module_graph() -> dict[str, set[str]]:
    mods = {}
    for p in sorted((PKG / "lib").rglob("*.py")):
        parts = list(p.relative_to(PKG).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        mods[".".join(parts)] = p
    graph: dict[str, set[str]] = {m: set() for m in mods}
    for m, p in mods.items():
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):  # function-level imports count too
            names = [a.name for a in n.names] if isinstance(n, ast.Import) else (
                [n.module, *(f"{n.module}.{a.name}" for a in n.names)] if isinstance(n, ast.ImportFrom)
                and n.module and n.level == 0 else [])
            graph[m] |= {x for x in names if x in mods and x != m}
    return graph


def cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    index, low, stack, on, out, counter = {}, {}, [], set(), [], [0]

    def visit(v: str) -> None:
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        for w in sorted(graph[v]):
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                out.append(sorted(comp))
    for v in sorted(graph):
        if v not in index:
            visit(v)
    return out


def test_no_import_cycle_in_the_kit():
    assert cycles(_module_graph()) == []


def test_the_cycle_sensor_sees_a_cycle():
    assert cycles({"a": {"b"}, "b": {"c"}, "c": {"a"}, "d": set()}) == [["a", "b", "c"]]
