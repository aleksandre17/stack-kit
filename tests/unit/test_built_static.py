"""The built-SPA fitness check (ADR-001 amendment 14): an address baked into what the browser runs
is refused; prose shipped beside it is not code."""
from __future__ import annotations

from lib.delivery.checks import built_static


def test_an_address_in_served_code_is_refused():
    found = built_static({"main.js": b'fetch("http://api.example.test/x")', "index.html": b"<a href='10.1.2.3'>"})
    assert any("main.js: http://api.example.test" in f for f in found)
    assert any("index.html: 10.1.2.3" in f for f in found)


def test_a_licence_text_is_prose_not_code():
    assert built_static({"3rdpartylicenses.txt": b"see http://www.apache.org/licenses/"}) == []


def test_an_allowed_address_passes():
    assert built_static({"main.js": b'"http://api.example.test"'}, ["http://api.example.test"]) == []
