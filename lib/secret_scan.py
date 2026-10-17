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

The four pattern rules above are the kit's BUILT-IN set, used only when the host declares none. A host
declares its own as documents of agent-kit's edit-gate contract, read by path (`security.secretPatterns`:
one path or several; the kit imports nothing of agent-kit): each gate is a rule -- its `id`, `forbids`
(the pattern, applied to each line), `paths` (the files it holds) -- and is used only once its own
calibration holds: `proves` must be refused and `admits` admitted, else the scan refuses to run on it.
The structural rules (env-file, tooling-binary, known-leak) always hold.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

RULES = {
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    "url-password": re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s:/@'\"]+:([^\s@/'\"]{3,})@[^\s/'\"]+", re.I),
    # a connection string: a server-like key, then a password-like key, in one `;`-separated value
    "connection-string": re.compile(r"(?i)\b(?:server|host|data source|addr|address|endpoint|accountname)\s*=[^;'\"]*;[^'\"]*?"
                                    r"\b(?:password|pwd|accountkey|sharedaccesskey)\s*=\s*([^;'\"\s]{3,})"),
    # a connection string that names its password first
    "connection-string-password-first": re.compile(r"(?i)\b(?:password|pwd)\s*=\s*([^;'\"\s]{3,})\s*;[^'\"]*?"
                                                   r"\b(?:server|host|data source|addr|address)\s*="),
    "aws-access-key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "github-token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    # the armour of a real key: alone on its line, or followed by its base64 body (a pattern naming it is not one)
    "private-key": re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----(?:\s*$|\\n[A-Za-z0-9+/=]{16})"),
}
PLACEHOLDER = re.compile(r"^(?:__[A-Z0-9_]+__|\$\{[^}]*\}|\$[A-Z_][A-Z0-9_]*|<[^>]*>|\{[^}]*\}|change_?me|example|xxx+|\*+|"
                         r"password|secret|pass|placeholder|redacted|dummy|test|ci|none|null)$", re.I)
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)")
ENV_FILE = re.compile(r"(^|/)(\.env(\.[^/]+)?|[^/]+\.env)$")
TOOLING = ("ops/", "tools/", "scripts/", "ci/")
#: What an executable or an archive of them starts with (PE, ELF, Mach-O, zip, class files).
BINARY_MAGIC = (b"MZ", b"\x7fELF", b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa", b"PK\x03\x04", b"\xca\xfe\xba\xbe")


class ScanError(ValueError):
    """A declared pattern document the scan cannot believe: missing, malformed, or uncalibrated."""


@dataclass(frozen=True)
class Rule:
    id: str
    pattern: re.Pattern[str]
    paths: re.Pattern[str] | None = None
    #: A declared gate decides what is a placeholder in its own pattern (agent-kit's gates refuse by a
    #: lookahead); its groups name what it matched, not a value -- so no second placeholder test.
    declared: bool = False

    def holds(self, path: str) -> bool:
        return self.paths is None or bool(self.paths.search(path))


BUILT_IN = [Rule(k, v) for k, v in RULES.items()]


def declared_documents(manifest: dict[str, Any]) -> list[str]:
    value = (manifest.get("security") or {}).get("secretPatterns")
    return [value] if isinstance(value, str) else [str(v) for v in value or []]


def _calibrated(rule: Rule, gate: dict[str, Any]) -> str:
    """Why a gate's calibration fails, or "" (it refuses what it `proves` and admits what it `admits`)."""
    proves, admits = gate.get("proves") or {}, gate.get("admits") or {}
    if not (rule.holds(str(proves.get("path") or "")) and rule.pattern.search(str(proves.get("text") or ""))):
        return "it does not refuse its own `proves`"
    if rule.holds(str(admits.get("path") or "")) and rule.pattern.search(str(admits.get("text") or "")):
        return "it refuses its own `admits`"
    return ""


def rules(root: Path, manifest: dict[str, Any]) -> list[Rule]:
    """The pattern rules a scan applies: the declared documents' gates, else the built-in set."""
    docs = declared_documents(manifest)
    if not docs:
        return BUILT_IN
    out: list[Rule] = []
    for rel in docs:
        p = root / rel
        if not p.is_file():
            raise ScanError(f"security.secretPatterns: {rel} is not there")
        try:
            doc = json.loads(p.read_text(encoding="utf-8-sig"))
        except ValueError as e:
            raise ScanError(f"security.secretPatterns: {rel} is not JSON ({e})") from e
        gates = doc.get("gates") if isinstance(doc, dict) else None
        if not isinstance(gates, list) or not gates:
            raise ScanError(f"security.secretPatterns: {rel} declares no `gates` (agent-kit's edit-gate contract)")
        for gate in gates:
            try:
                rule = Rule(str(gate["id"]), re.compile(str(gate["forbids"]), re.M),
                            re.compile(str(gate["paths"])) if gate.get("paths") else None, declared=True)
            except (KeyError, TypeError, re.error) as e:
                raise ScanError(f"security.secretPatterns: {rel}: a gate is not one ({e})") from e
            why = _calibrated(rule, gate)
            if why:
                raise ScanError(f"security.secretPatterns: {rel}: gate {rule.id} is not believed -- {why}")
            out.append(rule)
    return out


def pattern_problems(root: Path, manifest: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(errors, warnings) for validate: a declared document the scan cannot believe; an allowance that
    names a rule the active set does not have (the built-in set is off once patterns are declared)."""
    try:
        active = rules(root, manifest)
    except ScanError as e:
        return [str(e)], []
    if not declared_documents(manifest):
        return [], []
    ids = {r.id for r in active} | {"env-file", "tooling-binary", "known-leak"}
    allow, _known = policy(manifest)
    warnings = [f"security.allow: {a.get('path')} names rule {a.get('rule')!r}, which the declared patterns do not have "
                f"(the built-in set is not used once security.secretPatterns is declared)"
                for a in allow if a.get("rule") and str(a["rule"]) not in ids]
    return [], warnings


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    where: str = "tree"
    #: What the rule matched -- held only to judge it against a tracked value; never printed, never written.
    value: str = field(default="", repr=False)

    def __str__(self) -> str:
        at = f"{self.path}:{self.line}" if self.line else self.path
        return f"{at}: {self.rule}" + (f" (in {self.where})" if self.where != "tree" else "")


def calibration_document(text: str) -> bool:
    """Whether a text is a document of the edit-gate contract -- `gates[]`, each carrying the specimen it
    must refuse (`proves`) and the one it must admit (`admits`). Its specimens are credential-SHAPED on
    purpose, so they are its calibration, never a leak: recognised by this shape wherever the document
    is (a taken copy, a vendored kit), never by its path."""
    try:
        doc = json.loads(text.lstrip("\ufeff"))
    except ValueError:
        return False
    gates = doc.get("gates") if isinstance(doc, dict) else None
    return isinstance(gates, list) and bool(gates) and all(
        isinstance(g, dict) and isinstance(g.get("proves"), dict) and isinstance(g.get("admits"), dict)
        and "forbids" in g for g in gates)


def _value_of(rule: str, m: re.Match[str]) -> str:
    return m.group(1) if m.groups() else m.group(0)


def scan_text(path: str, text: str, known: set[str] | None = None, active: list[Rule] | None = None) -> list[Finding]:
    found: list[Finding] = []
    held = [r for r in (BUILT_IN if active is None else active) if r.holds(path)]
    for n, line in enumerate(text.splitlines(), 1):
        for r in held:
            for m in r.pattern.finditer(line):
                value = _value_of(r.id, m).strip("'\"")
                if not r.declared and r.id != "private-key" and PLACEHOLDER.match(value):
                    continue
                found.append(Finding(path, n, r.id, value=m.group(0)))  # every match: one line may hold several
        if known:
            for token in re.findall(r"[A-Za-z0-9+/=_\-.]{12,}", line):
                if hashlib.sha256(token.encode("utf-8")).hexdigest() in known:
                    found.append(Finding(path, n, "known-leak"))
    return found


def scan_path(path: str, data: bytes, known: set[str] | None = None, active: list[Rule] | None = None) -> list[Finding]:
    found: list[Finding] = []
    if ENV_FILE.search(path) and not path.endswith((".example", ".template", ".sample")):
        found.append(Finding(path, 0, "env-file"))
    if path.startswith(TOOLING) and data.startswith(BINARY_MAGIC):
        found.append(Finding(path, 0, "tooling-binary"))
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):  # UTF-16 with its mark -- what Windows tools often write
        return found + scan_text(path, data.decode("utf-16", "replace"), known, active)
    if b"\0" in data[:4096]:
        return found
    return found + scan_text(path, data.decode("utf-8", "replace"), known, active)


def known_exposures(root: Path, manifest: dict[str, Any]) -> dict[str, set[str]]:
    """file -> the KEYS the configuration catalogue tracks to their removal there (`knownExposures`).

    A known exposure is a key in a file, never the file: a finding is known only on the line that
    carries that key (its leaf name, quoted, followed by a colon), so a NEW secret added to the same
    file is still a finding (ADR-001 amendment 20 -- the scan once dropped every finding in such a file
    and reported the tree clean over seven committed secrets)."""
    rel = (manifest.get("config") or {}).get("keys")
    p = root / str(rel) if rel else None
    if not p or not p.is_file():
        return {}
    try:
        rows = json.loads(p.read_text(encoding="utf-8-sig")).get("knownExposures") or []
    except ValueError:
        return {}
    out: dict[str, set[str]] = {}
    for row in rows:
        if isinstance(row, dict) and row.get("file") and row.get("key"):
            out.setdefault(str(row["file"]), set()).add(str(row["key"]).replace("__", ":"))
    return out


def values_at(text: str, keys: set[str]) -> "set[str] | None":
    """The string values a JSON document holds at these configuration key paths (`A:B:C`, matched as the
    configuration system matches them, without case), or None when the text is not a JSON document."""
    try:
        doc = json.loads(text.lstrip("\ufeff"))
    except ValueError:
        return None
    found: set[str] = set()
    for key in keys:
        cur = doc
        for part in key.split(":"):
            cur = next((v for k, v in cur.items() if k.lower() == part.lower()), None) if isinstance(cur, dict) else None
        if isinstance(cur, str) and len(cur) >= 4:
            found.add(cur)
    return found


def _known(f: Finding, text_of, exposures: dict[str, set[str]], values_of=None) -> bool:
    """A finding is KNOWN only where it is the very value the catalogue tracks: in a JSON document, the line
    carries the value that stands at a tracked key path; elsewhere, the line IS that key's own line (its leaf
    as a whole name, at the start of the line). A new secret under another key, or inside another value,
    is a finding -- whatever it shares with a tracked one by name."""
    keys = exposures.get(f.path)
    if not keys:
        return False
    line = text_of(f)
    if not line:
        return False
    values = values_of(f) if values_of else None
    if values is not None:
        seen = f.value or line
        return any(value in seen or (f.value and f.value in value) for value in values)
    return any(re.match(rf'^\s*["\']?{re.escape(key.split(":")[-1])}["\']?\s*[:=]', line) for key in keys)


def tracked_split(findings: list[Finding], text_of, exposures: dict[str, set[str]],
                  values_of=None) -> tuple[list[Finding], list[Finding]]:
    """(findings, known): a finding that is a value the catalogue tracks is KNOWN -- counted and named as
    such, never reported clean and never failed twice."""
    known = [f for f in findings if _known(f, text_of, exposures, values_of)]
    return [f for f in findings if f not in known], known


def _allowed(f: Finding, allow: list[dict[str, Any]]) -> bool:
    return any(fnmatch.fnmatch(f.path, str(a.get("path"))) and str(a.get("rule", f.rule)) == f.rule and a.get("reason")
               for a in allow)


def policy(manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], set[str]]:
    sec = manifest.get("security") or {}
    return [a for a in sec.get("allow") or [] if isinstance(a, dict)], {str(h).lower() for h in sec.get("knownLeaks") or []}


def tree(root: Path, manifest: dict[str, Any]) -> list[Finding]:
    allow, known = policy(manifest)
    active = rules(root, manifest)
    out = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True)
    files = [p for p in out.stdout.decode("utf-8", "replace").split("\0") if p] if out.returncode == 0 else []
    found: list[Finding] = []
    for rel in files:
        p = root / rel
        if p.is_file() and p.stat().st_size < 2_000_000:
            found += scan_path(rel, p.read_bytes(), known, active)
    documents = set(declared_documents(manifest))  # a gate document carries its calibration
    lines: dict[str, list[str]] = {}

    def text_of(f: Finding) -> str:
        if f.path not in lines:
            lines[f.path] = (root / f.path).read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[f.path][f.line - 1] if 0 < f.line <= len(lines[f.path]) else ""

    exposures = known_exposures(root, manifest)
    held: dict[str, "set[str] | None"] = {}

    def values_of(f: Finding):
        if f.path not in held:
            held[f.path] = values_at((root / f.path).read_text(encoding="utf-8", errors="replace"), exposures[f.path])
        return held[f.path]

    calibrations: dict[str, bool] = {}

    def calibration(rel: str) -> bool:
        if rel not in calibrations:
            calibrations[rel] = rel.endswith(".json") and calibration_document(
                (root / rel).read_text(encoding="utf-8", errors="replace"))
        return calibrations[rel]

    left = [f for f in found if not _allowed(f, allow) and f.path not in documents and not calibration(f.path)]
    failing, known = tracked_split(left, text_of, exposures, values_of)
    KNOWN.clear()
    KNOWN.extend(known)
    return failing


def history(root: Path, manifest: dict[str, Any]) -> list[Finding]:
    """Every line any commit added: a secret removed from the tree is still in history. Each finding
    carries the line it was added at (the hunk's new-side start), so two in one commit and file are two --
    a known exposure never hides a new secret added beside it (ADR-001 amendment 20)."""
    allow, known = policy(manifest)
    active = rules(root, manifest)
    ran = subprocess.run(["git", "-C", str(root), "-c", "core.quotepath=off", "log", "--all", "-p", "--no-color",
                          "--unified=0", "--text", "--no-textconv", "--no-ext-diff", "--format=commit %H"],
                         capture_output=True)
    found: list[tuple[Finding, str]] = []
    commit, path, at = "", "", 0
    for raw in ran.stdout.decode("utf-8", "replace").split("\n"):
        raw = raw.rstrip("\r")
        if raw.startswith("commit "):
            commit = raw[7:19]
        elif raw.startswith("+++ "):
            named = raw[4:]
            if named.startswith('"') and named.endswith('"'):  # a name git quotes: unescape it
                named = named[1:-1].encode("latin-1", "backslashreplace").decode("unicode_escape").encode(
                    "latin-1", "replace").decode("utf-8", "replace")
            path = named[2:] if named.startswith("b/") else ""
            if path and ENV_FILE.search(path) and not path.endswith((".example", ".template", ".sample")):
                found.append((Finding(path, 0, "env-file", f"commit {commit}"), ""))
        elif raw.startswith("@@"):
            hunk = HUNK.match(raw)
            at = int(hunk.group(1)) if hunk else 0
        elif raw.startswith("+") and path:
            found += [(Finding(f.path, at, f.rule, f"commit {commit}", value=f.value), raw[1:])
                      for f in scan_text(path, raw[1:], known, active)]
            at += 1
    documents = set(declared_documents(manifest))
    added = {f: text for f, text in found}
    exposures = known_exposures(root, manifest)
    held: dict[tuple[str, str], "set[str] | None"] = {}

    def values_of(f: Finding):
        key = (f.where, f.path)
        if key not in held:
            shown = subprocess.run(["git", "-C", str(root), "show", f"{f.where.split()[-1]}:{f.path}"], capture_output=True)
            held[key] = values_at(shown.stdout.decode("utf-8", "replace"), exposures[f.path]) if shown.returncode == 0 else None
        return held[key]

    calibrations: dict[tuple[str, str], bool] = {}

    def calibration(f: Finding) -> bool:
        key = (f.where, f.path)
        if key not in calibrations:
            shown = subprocess.run(["git", "-C", str(root), "show", f"{f.where.split()[-1]}:{f.path}"],
                                   capture_output=True) if f.path.endswith(".json") else None
            calibrations[key] = bool(shown and shown.returncode == 0
                                     and calibration_document(shown.stdout.decode("utf-8", "replace")))
        return calibrations[key]

    left = [f for f in added if not _allowed(f, allow) and f.path not in documents and not calibration(f)]
    failing, known_found = tracked_split(left, added.get, exposures, values_of)
    KNOWN.clear()
    KNOWN.extend(known_found)
    return sorted(set(failing), key=lambda f: (f.path, f.where, f.line, f.rule))


#: The findings the last scan read as KNOWN exposures -- tracked by the catalogue to their removal.
KNOWN: list[Finding] = []


def report(findings: Iterable[Finding]) -> list[str]:
    return [str(f) for f in findings]


def fingerprint(value: str) -> str:
    """What an operator lists in security.knownLeaks for a leaked value (never the value itself)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main_lines(root: Path, manifest: dict[str, Any], with_history: bool) -> list[str]:
    """The findings of the tree and, on request, its history; KNOWN then holds both scans' known ones."""
    lines = report(tree(root, manifest))
    if with_history:
        in_tree = list(KNOWN)
        lines += report(history(root, manifest))
        KNOWN[:0] = in_tree
    return lines


def as_json(findings: Iterable[Finding]) -> str:
    return json.dumps([{k: v for k, v in f.__dict__.items() if k != "value"} for f in findings], indent=1)
