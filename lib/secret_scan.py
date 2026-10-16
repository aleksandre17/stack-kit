"""The secret boundary, structurally (ADR-001 amendment 14): what a credential LOOKS like, in every
tracked file and, on request, in every commit -- a value is never printed, only where and what kind.

    jwt                a three-part base64url token beginning eyJ
    url-password       scheme://user:password@host
    connection-string  Password= / Pwd= / AccountKey= with a value in a connection string
    private-key        PEM private key armour
    env-file           a committed .env, .env.<x> or *.env (an example is never one)
    tooling-binary     an executable binary in the tooling directories (ops/, tools/, scripts/, ci/)
    known-leak         a value whose sha256 the operator lists as leaked (`security.knownLeaks`)

A placeholder is not a value (`__NAME__`, `${NAME}`, `<...>`, `changeme`, `example`, `***`), and a host
may allow a finding by path and rule with its reason (`security.allow`).
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

RULES = {
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    "url-password": re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s:/@'\"]+:([^\s@/'\"]{3,})@[^\s/'\"]+", re.I),
    # a connection string: a server-like key, then a password-like key, in one `;`-separated value
    "connection-string": re.compile(r"(?i)\b(?:server|host|data source|addr|address|endpoint|accountname)\s*=[^;'\"]*;[^'\"]*?"
                                    r"\b(?:password|pwd|accountkey|sharedaccesskey)\s*=\s*([^;'\"\s]{3,})"),
    # the armour of a real key: alone on its line, or followed by its base64 body (a pattern naming it is not one)
    "private-key": re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----(?:\s*$|\\n[A-Za-z0-9+/=]{16})"),
}
PLACEHOLDER = re.compile(r"^(?:__[A-Z0-9_]+__|\$\{[^}]*\}|\$[A-Z_][A-Z0-9_]*|<[^>]*>|\{[^}]*\}|change_?me|example|xxx+|\*+|"
                         r"password|secret|pass|placeholder|redacted|dummy|test|ci|none|null)$", re.I)
ENV_FILE = re.compile(r"(^|/)(\.env(\.[^/]+)?|[^/]+\.env)$")
TOOLING = ("ops/", "tools/", "scripts/", "ci/")
#: What an executable or an archive of them starts with (PE, ELF, Mach-O, zip, class files).
BINARY_MAGIC = (b"MZ", b"\x7fELF", b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa", b"PK\x03\x04", b"\xca\xfe\xba\xbe")


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    where: str = "tree"

    def __str__(self) -> str:
        at = f"{self.path}:{self.line}" if self.line else self.path
        return f"{at}: {self.rule}" + (f" (in {self.where})" if self.where != "tree" else "")


def _value_of(rule: str, m: re.Match[str]) -> str:
    return m.group(1) if m.groups() else m.group(0)


def scan_text(path: str, text: str, known: set[str] | None = None) -> list[Finding]:
    found: list[Finding] = []
    for n, line in enumerate(text.splitlines(), 1):
        for rule, rx in RULES.items():
            for m in rx.finditer(line):
                value = _value_of(rule, m).strip("'\"")
                if rule != "private-key" and PLACEHOLDER.match(value):
                    continue
                found.append(Finding(path, n, rule))
                break
        if known:
            for token in re.findall(r"[A-Za-z0-9+/=_\-.]{12,}", line):
                if hashlib.sha256(token.encode("utf-8")).hexdigest() in known:
                    found.append(Finding(path, n, "known-leak"))
    return found


def scan_path(path: str, data: bytes, known: set[str] | None = None) -> list[Finding]:
    found: list[Finding] = []
    if ENV_FILE.search(path) and not path.endswith((".example", ".template", ".sample")):
        found.append(Finding(path, 0, "env-file"))
    if path.startswith(TOOLING) and data.startswith(BINARY_MAGIC):
        found.append(Finding(path, 0, "tooling-binary"))
    if b"\0" in data[:4096]:
        return found
    return found + scan_text(path, data.decode("utf-8", "replace"), known)


def known_exposures(root: Path, manifest: dict[str, Any]) -> set[str]:
    """Files the configuration catalogue already tracks to their removal (`knownExposures`): reported
    there, with their work, and not failed twice."""
    rel = (manifest.get("config") or {}).get("keys")
    p = root / str(rel) if rel else None
    if not p or not p.is_file():
        return set()
    try:
        return {str(e.get("file")) for e in json.loads(p.read_text(encoding="utf-8-sig")).get("knownExposures") or []}
    except ValueError:
        return set()


def _allowed(f: Finding, allow: list[dict[str, Any]]) -> bool:
    return any(fnmatch.fnmatch(f.path, str(a.get("path"))) and str(a.get("rule", f.rule)) == f.rule and a.get("reason")
               for a in allow)


def policy(manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], set[str]]:
    sec = manifest.get("security") or {}
    return [a for a in sec.get("allow") or [] if isinstance(a, dict)], {str(h).lower() for h in sec.get("knownLeaks") or []}


def tree(root: Path, manifest: dict[str, Any]) -> list[Finding]:
    allow, known = policy(manifest)
    out = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True)
    files = [p for p in out.stdout.decode("utf-8", "replace").split("\0") if p] if out.returncode == 0 else []
    found: list[Finding] = []
    for rel in files:
        p = root / rel
        if p.is_file() and p.stat().st_size < 2_000_000:
            found += scan_path(rel, p.read_bytes(), known)
    tracked = known_exposures(root, manifest)
    return [f for f in found if not _allowed(f, allow) and f.path not in tracked]


def history(root: Path, manifest: dict[str, Any]) -> list[Finding]:
    """Every line any commit added: a secret removed from the tree is still in history."""
    allow, known = policy(manifest)
    ran = subprocess.run(["git", "-C", str(root), "log", "--all", "-p", "--no-color", "--unified=0", "--format=commit %H"],
                         capture_output=True)
    found: list[Finding] = []
    commit, path = "", ""
    for raw in ran.stdout.decode("utf-8", "replace").splitlines():
        if raw.startswith("commit "):
            commit = raw[7:19]
        elif raw.startswith("+++ b/"):
            path = raw[6:]
            if ENV_FILE.search(path) and not path.endswith((".example", ".template", ".sample")):
                found.append(Finding(path, 0, "env-file", f"commit {commit}"))
        elif raw.startswith("+") and not raw.startswith("+++"):
            found += [Finding(f.path, 0, f.rule, f"commit {commit}") for f in scan_text(path, raw[1:], known)]
    tracked = known_exposures(root, manifest)
    return sorted({f for f in found if not _allowed(f, allow) and f.path not in tracked}, key=lambda f: (f.path, f.where, f.rule))


def report(findings: Iterable[Finding]) -> list[str]:
    return [str(f) for f in findings]


def fingerprint(value: str) -> str:
    """What an operator lists in security.knownLeaks for a leaked value (never the value itself)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main_lines(root: Path, manifest: dict[str, Any], with_history: bool) -> list[str]:
    return report(tree(root, manifest)) + (report(history(root, manifest)) if with_history else [])


def as_json(findings: Iterable[Finding]) -> str:
    return json.dumps([f.__dict__ for f in findings], indent=1)
