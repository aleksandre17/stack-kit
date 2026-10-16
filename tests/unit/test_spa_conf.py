"""The hardened SPA server config renders with and without declared proxies (`container.proxy`)."""
from __future__ import annotations

from pathlib import Path

from lib import templating

SPA = Path(__file__).resolve().parents[2] / "drivers" / "_shared" / "static" / "spa.conf"


def test_a_module_without_proxies_renders_no_proxy_block():
    text = templating.render(SPA.read_text(encoding="utf-8"), {}, {"port": "8080", "mount": "/srv", "proxy": ""})
    assert "listen 8080;" in text and "location /api" not in text and "{proxy" not in text


def test_declared_proxies_are_rendered_in_place():
    block = "    location /api/ { proxy_pass http://api:8080; }\n"
    text = templating.render(SPA.read_text(encoding="utf-8"), {}, {"port": "8080", "mount": "/srv", "proxy": block})
    assert block.strip() in text
