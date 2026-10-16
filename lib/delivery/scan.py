"""The image vulnerability scan a release passes before it runs (ADR-001 amendment 14).

Declared by the host (`security.imageScan`), never on by surprise:

    scanner        the scanner image, pinned by digest (name@sha256:...) -- a floating scanner is a
                   different judge on every run; it runs on the target, beside the image it judges
    environments   where a release must be scanned (default: every environment)
    failOn         the lowest severity that refuses a release (default high)
    observeOnly    report, refuse nothing (a first rollout)
    maxDbAgeHours  a vulnerability database older than this refuses (default 120)
    vex            an OpenVEX document of waivers: a statement `not_affected` or `fixed` for a
                   vulnerability takes it out of the verdict (its justification is the document's)

The verdict and its counts are written beside the release ({release}/.stack-kit/scan.json): a
release of a commit without a scan where one is declared is refused.
"""
from __future__ import annotations

import json
import posixpath
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib import naming
from lib.delivery.context import Delivery, DeliveryError

SEVERITY = ["negligible", "low", "medium", "high", "critical"]
PINNED = re.compile(r"^[^@\s]+@sha256:[0-9a-f]{64}$")


def policy(manifest: dict[str, Any]) -> dict[str, Any]:
    return ((manifest.get("security") or {}).get("imageScan")) or {}


def problems(manifest: dict[str, Any]) -> list[str]:
    p = policy(manifest)
    if not p:
        return []
    out = []
    if not PINNED.match(str(p.get("scanner") or "")):
        out.append("security.imageScan.scanner: pin the scanner image by digest (name@sha256:<64 hex>)")
    if p.get("failOn") and str(p["failOn"]).lower() not in SEVERITY:
        out.append(f"security.imageScan.failOn: one of {', '.join(SEVERITY)}")
    return out


def required(ctx: Delivery) -> bool:
    p = policy(ctx.manifest)
    return bool(p) and (not p.get("environments") or ctx.environment in p["environments"])


def waivers(root: Path, p: dict[str, Any]) -> set[str]:
    if not p.get("vex"):
        return set()
    doc = json.loads((root / str(p["vex"])).read_text(encoding="utf-8"))
    out = set()
    for st in doc.get("statements") or []:
        if str(st.get("status")) in ("not_affected", "fixed"):
            vuln = st.get("vulnerability") or {}
            name = vuln.get("name") if isinstance(vuln, dict) else vuln
            if name:
                out.add(str(name))
    return out


def verdict(report: dict[str, Any], p: dict[str, Any], waived: set[str], now: datetime | None = None) -> tuple[list[str], dict[str, int]]:
    """(why it refuses, counts by severity) of one image's scan report."""
    floor = SEVERITY.index(str(p.get("failOn") or "high").lower())
    counts = {s: 0 for s in SEVERITY}
    refusing = []
    for m in report.get("matches") or []:
        v = m.get("vulnerability") or {}
        sev = str(v.get("severity") or "").lower()
        if sev in counts:
            counts[sev] += 1
        if sev in SEVERITY and SEVERITY.index(sev) >= floor and str(v.get("id")) not in waived:
            refusing.append(f"{v.get('id')} ({sev}) in {((m.get('artifact') or {}).get('name'))}")
    why = [f"{len(refusing)} finding(s) at or above {SEVERITY[floor]}: " + ", ".join(sorted(refusing)[:10])] if refusing else []
    built = (((report.get("descriptor") or {}).get("db") or {}).get("built") or "")
    if built:
        when = datetime.fromisoformat(str(built).replace("Z", "+00:00"))
        age = ((now or datetime.now(timezone.utc)) - when).total_seconds() / 3600
        if age > float(p.get("maxDbAgeHours") or 120):
            why.append(f"the vulnerability database is {age:.0f}h old (maxDbAgeHours {p.get('maxDbAgeHours') or 120})")
    else:
        why.append("the scan names no database build time: its age cannot be judged")
    return why, counts


def scan(ctx: Delivery, svc: list[Any], release: str) -> None:
    """Every image this release builds, judged; refused (exit 5) unless the policy holds."""
    if not required(ctx) or not ctx.commands["engine"]:
        return
    p = policy(ctx.manifest)
    if problems(ctx.manifest):
        raise DeliveryError("refused: " + "; ".join(problems(ctx.manifest)), 5)
    waived = waivers(ctx.root, p)
    failures = []
    for s in svc:
        if s.kind != "build":
            continue
        image = naming.remote_image(ctx.project, ctx.environment, s.id, release)
        r = ctx.run(ctx.engine("run", "--rm", "-v", "/var/run/docker.sock:/var/run/docker.sock:ro", str(p["scanner"]),
                               image, "-o", "json"), check=False)
        if ctx.plan:
            continue
        if r.code != 0 or not r.out.strip().startswith("{"):
            raise DeliveryError(f"refused: the scan of {image} did not run (exit {r.code}) -- no release without its scan", 5)
        report = json.loads(r.out)
        why, counts = verdict(report, p, waived)
        record = {"image": image, "release": release, "scanner": p["scanner"], "counts": counts, "refused": why,
                  "observeOnly": bool(p.get("observeOnly"))}
        ctx.transport.write(posixpath.join(ctx.places.of("releases", s), release, ".stack-kit", "scan.json"),
                            (json.dumps(record, indent=1, sort_keys=True) + "\n").encode("utf-8"))
        summary = ", ".join(f"{k} {v}" for k, v in counts.items() if v) or "nothing found"
        ctx.out(f"[scan] {s.id}: {summary}" + (f" -- {'; '.join(why)}" if why else ""))
        if why and not p.get("observeOnly"):
            failures.append(f"{s.id}: " + "; ".join(why))
    if failures:
        raise DeliveryError("refused by the image scan policy: " + " | ".join(failures), 5)
