"""A Spring module's port and health path are read from the app where it says them (found adopting a
foreign project: the compose asked `:8090/health` of an app declaring 8080 and `/actuator/health`), else
the driver's defaults stand. What was read is a drafted declaration, shown as such."""
from __future__ import annotations

from pathlib import Path

from lib import draft as drafter


def _tree(root: Path, files: dict) -> Path:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


POM = "<project><parent><artifactId>spring-boot-starter-parent</artifactId></parent>%s</project>"
ACTUATOR = "<dependency><artifactId>spring-boot-starter-actuator</artifactId></dependency>"


def _app(root):
    return next(m for m in drafter.draft(root)["modules"].values() if m["type"] == "java-boot")


def test_the_port_and_the_health_path_are_read_from_the_app(tmp_path):
    root = _tree(tmp_path / "a", {"pom.xml": POM % ACTUATOR,
                                  "src/main/resources/application.yml": "spring:\n  application:\n    name: x\nserver:\n  port: 8081\n"})
    assert _app(root)["container"] == {"port": 8081, "healthPath": "/actuator/health"}


def test_a_properties_file_says_it_too(tmp_path):
    root = _tree(tmp_path / "b", {"pom.xml": POM % "", "src/main/resources/application.properties": "server.port=9000\n"})
    assert _app(root)["container"] == {"port": 9000}, "no actuator: the driver's health path stands"


def test_an_app_that_says_nothing_keeps_the_drivers_defaults(tmp_path):
    root = _tree(tmp_path / "c", {"pom.xml": POM % ""})
    assert "container" not in _app(root)
