"""Driver registry, CLI aliases, stack-deploy plan."""
from __future__ import annotations

from pathlib import Path

from conftest import run_kit_cli


def _run_api(repo: Path, pkg: Path, *args: str) -> str:
    # repo/pkg are accepted for call-site compatibility; the cwd + env (PYTHONPATH,
    # GEOSTAT_PROJECT_ROOT -> synthetic fixture, GEOSTAT_KIT_ROOT) are owned by the
    # centralized run_kit_cli harness so the child resolves `lib` and the fixture
    # manifest deterministically regardless of the cwd pytest was launched from.
    return run_kit_cli(*args).stdout.strip()


class TestJavaBootDriver:
    def test_commands_include_dev(self, registry: dict):
        cmds = set(registry["java-boot"]["commands"].keys())
        assert "deploy" in cmds
        assert "dev" in cmds
        assert "run" in cmds
        assert "watch" not in cmds

    def test_dev_script_exists(self, pkg_root: Path):
        assert (pkg_root / "drivers" / "java-boot" / "sh" / "dev.sh").is_file()

    def test_run_script_exists(self, pkg_root: Path):
        assert (pkg_root / "drivers" / "java-boot" / "ps1" / "run.ps1").is_file()
        assert (pkg_root / "toolkit" / "hybrid" / "Invoke-HybridRun.ps1").is_file()

    def test_dev_remote_toolkit_exists(self, pkg_root: Path):
        assert (pkg_root / "toolkit" / "deploy" / "dev-remote.sh").is_file()


class TestNodeViteDriver:
    def test_commands_include_dev_not_top_level_watch(self, registry: dict):
        cmds = set(registry["node-vite"]["commands"].keys())
        assert "deploy" in cmds
        assert "dev" in cmds
        assert "run" in cmds
        assert "watch" not in cmds
        assert "manage" in cmds

    def test_deploy_script_exists(self, pkg_root: Path):
        assert (pkg_root / "drivers" / "node-vite" / "ps1" / "deploy.ps1").is_file()

    def test_dev_script_exists(self, pkg_root: Path):
        assert (pkg_root / "drivers" / "node-vite" / "ps1" / "dev.ps1").is_file()

    def test_run_script_exists(self, pkg_root: Path):
        assert (pkg_root / "drivers" / "node-vite" / "ps1" / "run.ps1").is_file()


class TestNodeApiDriver:
    def test_registered_with_api_role(self, registry: dict):
        assert "node-api" in registry
        assert "api" in registry["node-api"]["roles"]
        assert registry["node-api"]["runtime"] == "bash"

    def test_commands_match_java_boot_service_shape(self, registry: dict):
        cmds = set(registry["node-api"]["commands"].keys())
        # Service lifecycle parity with java-boot (deploy/dev/run/manage/compose/check/modules)
        assert {"deploy", "dev", "run", "manage", "compose", "check", "modules"} <= cmds
        assert "watch" not in cmds  # watch is a dev subcommand, never a top-level command

    def test_deploy_and_dev_are_bash(self, pkg_root: Path):
        assert (pkg_root / "drivers" / "node-api" / "sh" / "deploy.sh").is_file()
        assert (pkg_root / "drivers" / "node-api" / "sh" / "dev.sh").is_file()

    def test_run_is_powershell_like_java_boot(self, pkg_root: Path):
        # local host run delegates to the shared hybrid runner (ps1), as java-boot does
        assert (pkg_root / "drivers" / "node-api" / "ps1" / "run.ps1").is_file()

    def test_node_step_helpers_exist(self, pkg_root: Path):
        deploy = pkg_root / "toolkit" / "deploy"
        assert (deploy / "pnpm-build.sh").is_file()
        assert (deploy / "node-upload.sh").is_file()
        assert (deploy / "node-docker-up.sh").is_file()


class TestManifest:
    def test_ui_module_type(self, manifest: dict):
        assert manifest["modules"]["web"]["type"] == "node-vite"

    def test_api_module_type(self, manifest: dict):
        assert manifest["modules"]["api"]["type"] == "java-boot"

    def test_node_api_module_type(self, manifest: dict):
        assert manifest["modules"]["svc"]["type"] == "node-api"

    def test_ui_alias(self, repo_root: Path, pkg_root: Path):
        assert _run_api(repo_root, pkg_root, "alias", "w") == "web"

    def test_stack_deploy_from_compose_modules(self, repo_root: Path, pkg_root: Path, manifest: dict):
        """stackDeploy.steps omitted — stack.composeModules drives remote deploy."""
        assert "stackDeploy" not in manifest or not manifest.get("stackDeploy", {}).get("steps")
        out = _run_api(repo_root, pkg_root, "stack-steps", "--prod")
        lines = [ln for ln in out.splitlines() if ln.strip()]
        modules = [ln.split("	")[0] for ln in lines]
        for mid in ("api", "search", "worker", "web"):
            assert mid in modules
        assert modules.index("api") < modules.index("worker")
        assert modules.index("worker") < modules.index("web")
        ui_line = [ln for ln in lines if ln.startswith("web	")][0]
        assert "dist" in ui_line


class TestDriverPaths:
    def test_deploy_path_resolves(self, repo_root: Path, pkg_root: Path):
        p = _run_api(repo_root, pkg_root, "path", "web", "deploy")
        assert p.endswith("deploy.ps1")

    def test_dev_path_resolves(self, repo_root: Path, pkg_root: Path):
        p = _run_api(repo_root, pkg_root, "path", "web", "dev")
        assert p.endswith("dev.ps1")

    def test_api_alias_resolves(self, repo_root: Path, pkg_root: Path):
        assert _run_api(repo_root, pkg_root, "alias", "a") == "api"

    def test_api_dev_path_via_alias(self, repo_root: Path, pkg_root: Path):
        p = _run_api(repo_root, pkg_root, "path", "a", "dev")
        assert p.endswith("dev.sh")

    def test_api_run_path_via_alias(self, repo_root: Path, pkg_root: Path):
        p = _run_api(repo_root, pkg_root, "path", "a", "run")
        assert p.endswith("run.ps1")

    def test_ui_run_path_resolves(self, repo_root: Path, pkg_root: Path):
        p = _run_api(repo_root, pkg_root, "path", "web", "run")
        assert p.endswith("run.ps1")
