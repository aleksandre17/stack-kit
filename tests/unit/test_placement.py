"""Init and extension templates are placed for the host (ADR-001 amendment 16.11): a tier's files go
where the host's module of that tier lives, its secrets folder is that module's, and a relative path
back to the root is counted from there -- else the layout profile's tier path, else `apps/<tier>`.
The fixture lays its modules out as a real host does (platform/apps/<app>/{backend,frontend}/...)."""
from __future__ import annotations

import json
from pathlib import Path

from lib import extend

HOST = {"version": 2, "package": "platform/kits/stack-kit", "project": "shop", "secrets": "ops/config/projects/shop",
        "layout": {"profile": "monorepo"},
        "modules": {"api": {"type": "dotnet-aspnet", "role": "api", "path": "platform/apps/shop/backend/api", "secretsModule": "api"},
                    "web": {"type": "node-spa", "role": "ui", "path": "platform/apps/shop/frontend/web", "secretsModule": "web"}}}


def _host(tmp_path: Path, manifest: dict) -> Path:
    root = tmp_path / "host"
    root.mkdir()
    (root / "stack-kit.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def test_init_places_each_tiers_files_with_the_hosts_modules(tmp_path):
    root = _host(tmp_path, HOST)
    extend.init(root)
    assert (root / "platform/apps/shop/backend/api/logs/.gitignore").is_file()
    assert (root / "platform/apps/shop/frontend/web/nginx.conf.template").is_file()
    assert (root / "ops/config/projects/shop/web/nginx.env.example").is_file()
    assert (root / "ops/config/projects/shop/api/.env.example").is_file()
    assert not (root / "apps").exists() and not (root / "ops/config/backend").exists(), "no default tree beside the host's"
    nginx = (root / "platform/apps/shop/frontend/web/nginx.conf.template").read_text(encoding="utf-8")
    assert "ops/config/projects/shop/web/nginx.env" in nginx and "<secrets:" not in nginx


def test_a_template_is_placed_with_the_way_back_from_the_module(tmp_path):
    root = _host(tmp_path, HOST)
    extend.copy_placed("scaffold/ops/compose/catalog.minimal.json", root, "ops/compose/catalog.json")
    text = (root / "ops/compose/catalog.json").read_text(encoding="utf-8")
    assert '"platform/apps/shop/backend/api/docker-compose.dev.yml"' in text
    assert '"../../../../../ops/config/projects/shop/api"' in text and "<tier:" not in text and "<up:" not in text


def test_without_modules_the_profile_places_them_and_without_a_profile_the_default(tmp_path):
    profiled = {k: v for k, v in HOST.items() if k != "modules"}
    assert extend.placed("<tier:backend>/x", profiled) == "platform/apps/shop/backend/x"
    assert extend.placed("<tier:frontend> <secrets:frontend> <up:frontend>", {}) == "apps/frontend frontend ../.."
