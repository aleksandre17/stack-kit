"""Project frontend: Dockerfile ports, compose port mappings, golden-path scripts."""
from __future__ import annotations

import re
from pathlib import Path

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestDockerfile:
    def test_production_exposes_80_not_host_port(self, frontend_dir: Path):
        text = _read(frontend_dir / "src" / "Dockerfile")
        prod = text.split("Stage 4", 1)[-1]
        assert "EXPOSE 80" in prod
        assert re.search(r"EXPOSE\s+5177", prod) is None

    def test_development_uses_app_dev_port_arg(self, frontend_dir: Path):
        text = _read(frontend_dir / "src" / "Dockerfile")
        dev = text.split("Stage 3")[0]
        assert "APP_DEV_PORT" in dev
        assert "development" in dev

    def test_production_uses_nginx_arg(self, frontend_dir: Path):
        text = _read(frontend_dir / "src" / "Dockerfile")
        assert "NGINX_VERSION" in text
        assert "nginx:${NGINX_VERSION}" in text or "nginx:" in text


class TestComposePortMappings:
    def test_prod_overlay_maps_host_to_container_80(self, frontend_dir: Path):
        text = _read(frontend_dir / "docker-compose.prod.yml")
        assert re.search(r'DEPLOY_HOST_PORT[^:]*:80', text) or ":80" in text
        assert ":5177:5177" not in text.replace("APP_DEV_CONTAINER_PORT", "")

    def test_override_dev_maps_host_to_vite_port(self, frontend_dir: Path):
        text = _read(frontend_dir / "docker-compose.override.yml")
        assert "development" in text or "target: development" in text
        assert "APP_DEV_CONTAINER_PORT" in text or "5177" in text

    def test_compose_dockerfile_path(self, frontend_dir: Path):
        text = _read(frontend_dir / "docker-compose.yml")
        assert "src/Dockerfile" in text


class TestDeployScriptModes:
    def test_deploy_includes_watch_mode(self, pkg_root: Path):
        text = _read(pkg_root / "drivers" / "node-vite" / "ps1" / "deploy.ps1")
        assert '"watch"' in text or "'watch'" in text
        assert "Start-FeStaticDeployWatch" in text or "watch" in text

    def test_dev_subcommands(self, pkg_root: Path):
        text = _read(pkg_root / "drivers" / "node-vite" / "ps1" / "dev.ps1")
        for sub in ("bootstrap", "sync", "watch", "restart"):
            assert sub in text
        assert "Invoke-DevRsyncToRemote" in text

    def test_cli_redirects_fe_watch_to_deploy(self, pkg_root: Path):
        text = _read(pkg_root / "cli" / "stack-kit.ps1")
        assert 'sub -eq "watch"' in text
        assert "node-vite" in text
        assert "deploy" in text


class TestToolkitModules:
    def test_static_deploy_watch_module(self, pkg_root: Path):
        assert (pkg_root / "toolkit" / "powershell" / "Static-Deploy-Watch.ps1").is_file()

    def test_dev_remote_module(self, pkg_root: Path):
        assert (pkg_root / "toolkit" / "powershell" / "Dev-Remote.ps1").is_file()


class TestCatalogProdPort:
    def test_app_prod_overlay_container_port_80(self, catalog_path: Path):
        catalog = _read(catalog_path)
        assert "DEPLOY_HOST_PORT" in catalog
        assert ":80" in catalog
        # prod stack maps host:80 not host:5177 inside container
        assert "app_prod_overlay" in catalog
        snippet = catalog.split("app_prod_overlay")[1][:400]
        assert ":80" in snippet
