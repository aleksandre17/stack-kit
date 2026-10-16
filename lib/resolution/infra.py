"""The local infra stack's compose files and tunnels -- what the manifest declares under
`stack.infra` (split from the resolver, ADR-001 amendment 13)."""
from __future__ import annotations

from pathlib import Path

from lib import identity
from lib.resolution.context import KIT_ROOT


class InfraAnswers:
    """Mixed into the Resolver: needs `self.ctx` and `self.env_value`."""

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
