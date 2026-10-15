"""Post-migration layout: paths, manifest, apps, ops, kit — no legacy gaps."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

# Runtime / config files that must not reference pre-v2 layout paths
CRITICAL_GLOBS = (
    "stack-kit.json",
    "apps/**/*.yml",
    "apps/**/*.yaml",
    "apps/**/*.js",
    "apps/**/docker-compose*.yml",
    "apps/**/ops.config.*",
    "ops/compose/catalog.json",
    "ops/compose/stack/*.yml",
    "ops/cli/*.ps1",
    "tools/stack-kit.ps1",
    ".github/workflows/*.yml",
)

LEGACY_PATH_FRAGMENTS = (
    "packages/stack-kit",
    "packages/stack-kit-ops",
    "infra/compose/catalog",
    "deploy/compose/",
    "../secrets/",
    "secrets/deploy.env",
)

# Match only path-like usage (env_file, import, context), not substring in apps/backend/...
LEGACY_PATH_REGEX = re.compile(
    r"(?:env_file|import|context|file:)[^\n]*"
    r"(?:\.\./secrets/|secrets/(?:backend|frontend)/|packages/stack-kit)",
    re.IGNORECASE,
)

REMOVED_ROOT_DIRS = ("packages", "secrets", "infra", "deploy", "scripts")

OPTIONAL_LEGACY_STUBS = ("frontend", "backend")  # empty stubs at root — should be deleted


def _manifest_paths(manifest: dict, repo_root: Path) -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    pkg = manifest.get("package", "kits/stack-kit")
    out.append(("package", repo_root.joinpath(*pkg.split("/"))))
    sec = manifest.get("secrets", "ops/config")
    out.append(("secrets", repo_root.joinpath(*sec.split("/"))))
    compose = manifest.get("compose", {})
    if cat := compose.get("catalog"):
        out.append(("compose.catalog", repo_root.joinpath(*cat.split("/"))))
    if sync := compose.get("syncModules"):
        out.append(("compose.syncModules", repo_root.joinpath(*sync.split("/"))))
    stack = manifest.get("stack", {})
    if sdir := stack.get("composeDir"):
        out.append(("stack.composeDir", repo_root.joinpath(*sdir.split("/"))))
    for mid, mod in manifest.get("modules", {}).items():
        out.append((f"modules.{mid}.path", repo_root.joinpath(*mod["path"].split("/"))))
    ci = manifest.get("ci", {})
    for key in ("integration", "prepareEnv", "waitHealth", "waitStackHealth"):
        if rel := ci.get(key):
            out.append((f"ci.{key}", repo_root.joinpath(*rel.split("/"))))
    adapter_file_keys = frozenset({"template", "output", "env", "envExample", "credentialsFile"})
    adapters = manifest.get("adapters", {})
    for name, cfg in adapters.items():
        if isinstance(cfg, dict):
            for k, rel in cfg.items():
                if k in adapter_file_keys and isinstance(rel, str) and "/" in rel:
                    out.append((f"adapters.{name}.{k}", repo_root.joinpath(*rel.split("/"))))
    return out


def _collect_critical_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for pattern in CRITICAL_GLOBS:
        files.extend(repo_root.glob(pattern))
    return sorted({p.resolve() for p in files if p.is_file()})


class TestManifestV2:
    def test_manifest_version(self, manifest: dict) -> None:
        assert manifest.get("version") == 2

    def test_package_path_is_kits(self, manifest: dict) -> None:
        assert manifest.get("package") == "kits/stack-kit"

    def test_all_manifest_paths_exist(self, repo_root: Path, manifest: dict) -> None:
        missing = []
        for label, path in _manifest_paths(manifest, repo_root):
            if path.exists():
                continue
            if label.endswith(".env"):
                ex = path.with_name(path.stem + ".env.example")
                if ex.is_file():
                    continue
            missing.append(f"{label}: {path.relative_to(repo_root)}")
        assert not missing, "missing:\n  " + "\n  ".join(missing)

    def test_package_dir_is_this_kit(self, repo_root: Path, manifest: dict, pkg_root: Path) -> None:
        pkg_path = repo_root.joinpath(*manifest["package"].split("/"))
        assert pkg_path.resolve() == pkg_root.resolve()


class TestV2RootLayout:
    def test_required_top_level_dirs(self, repo_root: Path) -> None:
        for name in ("apps", "kits", "ops", "docs", "tools"):
            assert (repo_root / name).is_dir(), f"missing {name}/"

    def test_apps_modules_exist(self, frontend_dir: Path, backend_dir: Path) -> None:
        assert (frontend_dir / "package.json").is_file()
        assert (backend_dir / "build.gradle").is_file() or (backend_dir / "build.gradle.kts").is_file()

    @pytest.mark.parametrize("name", REMOVED_ROOT_DIRS)
    def test_legacy_root_dirs_removed(self, repo_root: Path, name: str) -> None:
        assert not (repo_root / name).exists(), f"legacy dir still present: {name}/"

    def test_no_legacy_root_stubs(self, repo_root: Path) -> None:
        """Root frontend/ or backend/ are migration leftovers — only apps/* should hold code."""
        stubs = []
        for name in OPTIONAL_LEGACY_STUBS:
            p = repo_root / name
            if p.is_dir() and any(p.iterdir()):
                stubs.append(name)
        assert not stubs, f"remove root stubs (use apps/ only): {stubs}"


class TestNoLegacyPathsInCriticalFiles:
    @pytest.fixture
    def critical_files(self, repo_root: Path) -> list[Path]:
        return _collect_critical_files(repo_root)

    def test_critical_files_found(self, critical_files: list[Path]) -> None:
        assert len(critical_files) >= 10

    @pytest.mark.parametrize("fragment", LEGACY_PATH_FRAGMENTS)
    def test_no_legacy_fragment_in_critical_files(
        self, repo_root: Path, critical_files: list[Path], fragment: str
    ) -> None:
        hits: list[str] = []
        for path in critical_files:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if fragment in text:
                hits.append(f"{path.relative_to(repo_root)}: {fragment!r}")
        assert not hits, "\n".join(hits)

    def test_no_legacy_path_refs_in_runtime_config(
        self, repo_root: Path, critical_files: list[Path]
    ) -> None:
        hits: list[str] = []
        for path in critical_files:
            if path.name == "application.yml":
                continue  # top-level comment only; profiles hold imports
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for m in LEGACY_PATH_REGEX.finditer(text):
                hits.append(f"{path.relative_to(repo_root)}: {m.group(0)!r}")
        assert not hits, "\n".join(hits)


class TestAppsConfigWiring:
    def test_vite_env_dir_points_to_ops_config(self, frontend_dir: Path) -> None:
        text = (frontend_dir / "vite.config.js").read_text(encoding="utf-8")
        assert "ops/config/web" in text.replace("\\", "/")

    def test_spring_imports_ops_config(self, backend_dir: Path) -> None:
        for name in ("application-dev.yml", "application-prod.yml", "application-local.yml"):
            path = backend_dir / "src/main/resources" / name
            assert path.is_file(), name
            text = path.read_text(encoding="utf-8")
            assert "ops/config/api" in text.replace("\\", "/"), name

    def test_module_compose_use_ops_config(self, backend_dir: Path, frontend_dir: Path) -> None:
        for base in (backend_dir, frontend_dir):
            for yml in base.glob("docker-compose*.yml"):
                text = yml.read_text(encoding="utf-8")
                if "env_file" in text or "secrets_backend" in text:
                    norm = text.replace("\\", "/")
                    assert "ops/config" in norm, yml.name
                    assert "../secrets" not in norm, yml.name


class TestComposeCatalogAndStack:
    def test_catalog_targets_under_apps_or_ops(self, catalog_path: Path) -> None:
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
        for target in data.get("targets", {}):
            ok = target.startswith("apps/") or target.startswith("ops/")
            assert ok, f"catalog target not v2: {target}"

    def test_catalog_no_legacy_target_paths(self, catalog_path: Path) -> None:
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
        for target in data.get("targets", {}):
            assert not target.startswith("backend/"), target
            assert not target.startswith("frontend/"), target
            assert not target.startswith("deploy/"), target
        blob = json.dumps(data.get("fmt", {})) + json.dumps(
            {k: v.get("fmt", {}) for k, v in data.get("targets", {}).items()}
        )
        assert "../secrets/" not in blob
        assert "deploy/compose" not in blob

    def test_stack_compose_exists(self, repo_root: Path, manifest: dict) -> None:
        stack = repo_root.joinpath(*manifest["stack"]["composeDir"].split("/"))
        assert (stack / "docker-compose.yml").is_file()
        assert (stack / "docker-compose.prod.yml").is_file()

    def test_stack_compose_paths_to_apps(self, repo_root: Path, manifest: dict) -> None:
        stack = repo_root.joinpath(*manifest["stack"]["composeDir"].split("/"))
        text = (stack / "docker-compose.yml").read_text(encoding="utf-8")
        assert "apps/api" in text or "../../apps/api" in text
        assert "apps/web" in text or "../../apps/web" in text

    def test_stack_compose_includes_manifest_modules(self, repo_root: Path, manifest: dict) -> None:
        stack = repo_root.joinpath(*manifest["stack"]["composeDir"].split("/"))
        text = (stack / "docker-compose.yml").read_text(encoding="utf-8")
        for mid in ("search", "worker"):
            if mid in (manifest.get("modules") or {}):
                assert mid in text


class TestCliChain:
    def test_tools_shim_delegates_to_ops_cli(self, repo_root: Path) -> None:
        text = (repo_root / "tools" / "stack-kit.ps1").read_text(encoding="utf-8")
        assert "ops" in text and "cli" in text

    def test_ops_cli_delegates_to_kit(self, repo_root: Path, manifest: dict) -> None:
        text = (repo_root / "ops" / "cli" / "stack-kit.ps1").read_text(encoding="utf-8")
        assert manifest["package"].replace("/", "\\") in text or manifest["package"] in text

    def test_kit_cli_exists(self, pkg_root: Path) -> None:
        assert (pkg_root / "cli" / "stack-kit.ps1").is_file()


class TestKitPackageIntegrity:
    def test_compose_build_finds_repo_via_manifest(self, repo_root: Path, pkg_root: Path) -> None:
        # Behaviour, not spelling: compose-gen resolves the project the one discovery resolves.
        import importlib.util

        spec = importlib.util.spec_from_file_location("compose_build", pkg_root / "compose" / "build.py")
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        assert build.find_project_root().resolve() == repo_root.resolve()
        assert build.load_manifest(repo_root)["modules"]

    # Defaults and discovery are the resolver's (tests/test_resolver_parity.py), not a spelling here.

    def test_scaffold_v2_tree(self, pkg_root: Path) -> None:
        sc = pkg_root / "scaffold"
        assert (sc / "apps" / "frontend").is_dir()
        assert (sc / "apps" / "backend").is_dir()
        assert (sc / "ops" / "compose" / "catalog.full.json").is_file()
        assert not (sc / "infra").exists()
        assert not (sc / "secrets").exists()
