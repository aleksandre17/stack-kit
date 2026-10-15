"""`validate.stages`: a declared pipeline that ends on value anchors (ADR-001 decision 4).

What the prior system's ops proved works: one validation that brings the real stack up, migrates
it from nothing, builds, tests against it, checks health, loads data through the path production
uses, and then COMPARES A VALUE -- a row count, a known record -- before tearing everything down.
A green from such a run means the real path works. A pipeline that never compares a value proves
only that its commands exited 0, so a stage list without an anchor is refused, and so is one whose
last working stage is not an anchor (a stage after the last comparison is unproven).

A stage is `{"id", "kind", "run": [argv...]}`, optionally `cwd` (project-relative), `env`,
`timeout` (seconds). Kinds: setup, migrate, build, test, health, ingest, anchor, teardown. An
anchor also declares `expect`: exactly one of `equals` (text), `matches` (regex), `atLeast`
(number), compared with the stripped standard output of its command. Stages run in order and stop
at the first failure; every `teardown` stage runs afterwards whatever happened.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

KINDS = ("setup", "migrate", "build", "test", "health", "ingest", "anchor", "teardown")
EXPECTATIONS = ("equals", "matches", "atLeast")


def problems(stages: Any) -> list[str]:
    """Why a declared stage list cannot be run as a proof, or [] when it can."""
    if not isinstance(stages, list) or not stages:
        return ["validate.stages: declare at least one stage"]
    out: list[str] = []
    seen: set[str] = set()
    for i, stage in enumerate(stages):
        where = f"validate.stages[{i}]"
        if not isinstance(stage, dict):
            out.append(f"{where}: a stage is an object")
            continue
        sid = stage.get("id")
        if not sid:
            out.append(f"{where}: a stage needs an id")
        elif sid in seen:
            out.append(f"{where}: id '{sid}' is used twice")
        seen.add(str(sid))
        if stage.get("kind") not in KINDS:
            out.append(f"{where}: kind must be one of {', '.join(KINDS)}")
        run = stage.get("run")
        if not (isinstance(run, list) and run and all(isinstance(a, str) and a for a in run)):
            out.append(f"{where}: run is a non-empty argv list of strings")
        if stage.get("kind") == "anchor":
            expect = stage.get("expect")
            given = [k for k in EXPECTATIONS if isinstance(expect, dict) and k in expect]
            if len(given) != 1:
                out.append(f"{where}: an anchor declares exactly one of expect.{'/'.join(EXPECTATIONS)}")
    working = [s for s in stages if isinstance(s, dict) and s.get("kind") != "teardown"]
    if not any(s.get("kind") == "anchor" for s in working):
        out.append("validate.stages: no anchor -- a pipeline that never compares a value proves only "
                   "that its commands ran")
    elif working[-1].get("kind") != "anchor":
        out.append(f"validate.stages: the last working stage is '{working[-1].get('id')}', not an anchor -- "
                   "what runs after the last comparison is unproven")
    return out


def _compare(expect: dict[str, Any], seen: str) -> str | None:
    """None when the value holds, else the sentence that says how it does not."""
    if "equals" in expect:
        want = str(expect["equals"])
        return None if seen == want else f"expected {want!r}, got {seen!r}"
    if "matches" in expect:
        return None if re.search(str(expect["matches"]), seen) else f"expected to match {expect['matches']!r}, got {seen!r}"
    try:
        number = float(seen)
    except ValueError:
        return f"expected a number of at least {expect['atLeast']}, got {seen!r}"
    return None if number >= float(expect["atLeast"]) else f"expected at least {expect['atLeast']}, got {seen!r}"


def _run(root: Path, stage: dict[str, Any], capture: bool) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, **{str(k): str(v) for k, v in (stage.get("env") or {}).items()}}
    return subprocess.run(stage["run"], cwd=root / (stage.get("cwd") or "."), env=env, text=True,
                          capture_output=capture, timeout=stage.get("timeout"))


def run(root: Path, stages: list[dict[str, Any]], out=sys.stdout) -> int:
    """Run the pipeline. 0 when every stage held, 1 at the first that did not (teardown still runs)."""
    found = problems(stages)
    if found:
        for p in found:
            print(f"ERROR: {p}", file=sys.stderr)
        return 1
    working = [s for s in stages if s["kind"] != "teardown"]
    teardown = [s for s in stages if s["kind"] == "teardown"]
    failed: str | None = None
    try:
        for n, stage in enumerate(working, 1):
            label = f"[stage {n}/{len(working)}] {stage['id']} ({stage['kind']})"
            print(label, file=out, flush=True)
            started = time.monotonic()
            try:
                done = _run(root, stage, capture=stage["kind"] == "anchor")
            except (OSError, subprocess.TimeoutExpired) as e:
                failed = f"{label}: could not run -- {e}"
                break
            if done.returncode != 0:
                if done.stderr:
                    print(done.stderr, file=sys.stderr, end="")
                failed = f"{label}: exited {done.returncode}"
                break
            if stage["kind"] == "anchor":
                seen = (done.stdout or "").strip()
                print(f"  value: {seen}", file=out)
                why = _compare(stage["expect"], seen)
                if why:
                    failed = f"{label}: the anchor does not hold -- {why}"
                    break
            print(f"  ok ({time.monotonic() - started:.1f}s)", file=out, flush=True)
    finally:
        for stage in teardown:
            print(f"[teardown] {stage['id']}", file=out, flush=True)
            try:
                done = _run(root, stage, capture=False)
                if done.returncode != 0:
                    print(f"  teardown '{stage['id']}' exited {done.returncode}", file=sys.stderr)
            except (OSError, subprocess.TimeoutExpired) as e:
                print(f"  teardown '{stage['id']}' could not run -- {e}", file=sys.stderr)
    if failed:
        print(f"FAILED {failed}", file=sys.stderr)
        return 1
    print(f"[validate] {len(working)} stage(s) held, ending on an anchor", file=out)
    return 0
