"""The environment's answers for one project root: asked each time, never cached -- env files,
env values, the selected deploy target (ADR-001 decision 2, amendments 9, 13).

Every name is lib/naming.py's; every remote path is lib/targets/layout.py's. Nothing here reads a
deploy.env, an `.env.deploy` or a DEPLOY_* key: before 2.0.0 those were fallback homes of the server,
the project and the service names, and a host that still has one is refused by `validate`.
"""
from __future__ import annotations

from pathlib import Path

from lib import envfile, identity, naming
from lib.project_context import load_manifest
from lib.resolution.context import context
from lib.resolution.infra import InfraAnswers


class Resolver(InfraAnswers):
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

    def target(self) -> tuple[str, dict] | None:
        """(name, target) of the selected declared target -- `--target` (STACK_KIT_TARGET), else the
        environment's default, else the only one -- or None when the host declares none."""
        if self._target is False:
            from lib import targets

            data = targets.load(self.root, self.manifest)
            self._target = None if data is None else targets.select(
                data, identity.env("TARGET"), identity.env("ENVIRONMENT"), self.manifest)
        return self._target  # type: ignore[return-value]

    def ssh_args(self) -> list[str]:
        """The openssh options of the selected target; none for a target nothing can reach (the step
        that needs it is refused where it runs, naming why)."""
        from lib import targets

        try:
            chosen = self.target()
            if chosen is None:
                return []
            targets.reachable(*chosen)
        except targets.TargetError:
            return []
        return targets.ssh_args(self.root, *chosen)

    def compose_project(self, environment: str = "") -> str:
        from lib import catalogs

        env = environment or identity.env("ENVIRONMENT") or catalogs.default_environment("deploy", self.manifest)
        return naming.remote_compose_project(self.project_slug(), env)

    def project_slug(self) -> str:
        return naming.project_slug(self.manifest, self.root)

    def folders(self) -> list[str]:
        return [f for f in self.ctx.get("secretsFolders", "").split("\n") if f]

    def env_files(self, folder: str, profile: str = "all") -> list[Path]:
        from lib import catalogs

        return envfile.folder_files(self.secrets_root, folder, profile, catalogs.ids("environments", self.manifest))

    def env_value(self, folder: str, key: str, default: str = "") -> str:
        """The last non-empty value of `key` across the folder's env files, as compose would apply it."""
        return envfile.merged(self.env_files(folder)).get(key, default)

    def run_env(self, folder: str, environment: str = "") -> dict[str, str]:
        """The variables a run of the folder's module sets, for one environment (envfile.run_files)."""
        from lib import catalogs

        envs = catalogs.ids("environments", self.manifest)
        environment = environment or catalogs.default_environment("run", self.manifest)
        return envfile.merged(envfile.run_files(self.secrets_root, folder, environment, envs))
