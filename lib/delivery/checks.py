"""Checks a release must pass before it ships (ADR-001 amendment 14).

    built_static   a built single-page app carries no `http://` URL and no IP literal: an address
                   baked into the bundle is an environment compiled in (it belongs in runtime
                   config) and, over plain http, a mixed-content or downgrade hole
    image_tag      every image a release runs names a version (never `latest`, never none), and a
                   digest where the environment declares `requireDigests`: a floating tag is a
                   different image on the next pull
"""
from __future__ import annotations

import re

TEXT = (".js", ".mjs", ".cjs", ".html", ".css", ".json", ".map", ".txt", ".webmanifest")
#: URLs that are names, not addresses: XML namespaces and the like.
NAMESPACES = re.compile(r"http://(?:www\.w3\.org|ns\.adobe\.com|purl\.org|schemas\.\w+\.\w+|xmlns\.com)/")
HTTP = re.compile(r"http://[A-Za-z0-9.\-\[\]:]+")
IPV4 = re.compile(r"(?<![\w.])(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?![\w.])")
#: Dotted numbers that are versions, not addresses (a.b.c.d with a leading v or a semver context).
VERSIONISH = re.compile(r"(?:v|version[\"' :=]+|@)\s*$", re.I)


def built_static(tree: dict[str, bytes], allow: list[str] | None = None) -> list[str]:
    """Each baked-in address, by file and value (an address is not a secret)."""
    allowed = set(allow or [])
    found: list[str] = []
    for rel, data in sorted(tree.items()):
        if not rel.lower().endswith(TEXT) or rel.endswith(".map"):
            continue
        text = data.decode("utf-8", "replace")
        for m in HTTP.finditer(text):
            if NAMESPACES.match(text, m.start()) or m.group(0) in allowed:
                continue
            found.append(f"{rel}: {m.group(0)} (plain http baked in)")
        for m in IPV4.finditer(text):
            if m.group(0) in allowed or VERSIONISH.search(text[max(0, m.start() - 12):m.start()]):
                continue
            found.append(f"{rel}: {m.group(0)} (an IP address baked in)")
    return sorted(set(found))


def image_tag(image: str, *, require_digest: bool = False) -> str | None:
    """Why an image reference floats, or None when it is pinned enough."""
    ref = image.split("@", 1)
    name, digest = ref[0], ref[1] if len(ref) > 1 else ""
    tag = name.rsplit(":", 1)[1] if ":" in name.rsplit("/", 1)[-1] else ""
    if digest and re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        return None
    if not tag:
        return f"{image}: no tag -- it is `latest` on every pull"
    if tag == "latest":
        return f"{image}: `latest` floats"
    if require_digest:
        return f"{image}: no digest (@sha256:...) and the environment requires one"
    return None
