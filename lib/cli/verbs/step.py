"""Every lifecycle step the catalog declares (`build`, `test`, `lint`, or a host's own) is a verb
across the modules: in manifest order, fail-fast, each recorded. A module whose driver lacks the
step fails it -- unless the step is optional, which it skips and says. The verdict names every module
that ran nothing, and why: a module that ran nothing is never counted as one that ran (CWE-223)."""
from __future__ import annotations

import sys

from lib.cli import tools
from lib.cli.registry import Args, Verb


def steps() -> list[str]:
    from lib.modules import lifecycle_steps

    try:
        from lib.project_context import load_manifest

        return lifecycle_steps(load_manifest(tools.project_root()))
    except FileNotFoundError:
        return lifecycle_steps()


def verb_for(step: str) -> Verb:
    return Verb(step, f"the `{step}` step of every module (or the named ones)", [f"{step} [module ...]"],
                lambda a: run(step, a), passthrough=True, exits=(0, 1, 2))


def run(step: str, a: Args) -> int:
    from lib.cli.verbs.mod import alias
    from lib.modules import driver_commands, optional_steps
    from lib.project_context import load_manifest

    manifest = load_manifest(tools.project_root())
    modules = [m for m, c in (manifest.get("modules") or {}).items() if isinstance(c, dict)]
    if a.raw:
        wanted = []
        for w in a.raw:
            m = alias(w)
            if not m:
                print(f"  Unknown module or alias: {w}", file=sys.stderr)
                return 1
            wanted.append(m)
        modules = [m for m in modules if m in wanted]
    optional = optional_steps(manifest)
    ran: list[str] = []
    not_run: list[tuple[str, str]] = []
    for mid in modules:
        typ = str(manifest["modules"][mid].get("type") or "")
        if step not in driver_commands(typ):
            if step in optional:
                print(f"  [{mid} {step}] skipped: driver '{typ}' declares no {step}")
                not_run.append((mid, f"driver '{typ}' declares no {step}"))
                continue
            print(f"  [{mid} {step}] driver '{typ}' declares no {step} step")
            return 1
        said: list["str | None"] = []

        def act(module: str = mid) -> int:
            code, reason = tools.driver_step(module, step, [])
            said.append(reason)
            return code

        code = tools.recorded("step", step, mid, act, not_run=lambda: said[0] if said else None)
        if code:
            print(f"  [{mid} {step}] FAILED (exit {code})")
            return code
        if said and said[0]:
            not_run.append((mid, said[0]))
        else:
            ran.append(mid)
    print(verdict(step, ran, not_run))
    return 0


def verdict(step: str, ran: list[str], not_run: list[tuple[str, str]]) -> str:
    """The step's last line: what ran, and every module that ran nothing with why -- all of them named."""
    skipped = "; ".join(f"{mid} ({why})" for mid, why in not_run)
    if not ran:
        return f"  {step}: NOTHING RAN" + (f" -- not run: {skipped}" if skipped else " -- no module was selected")
    return f"  {step} OK ({len(ran)} module(s) ran" + (f"; not run: {skipped})" if skipped else ")")


VERB = Verb("<step>", "a lifecycle step (catalogs.lifecycle: lint, build, test, ...) for every module, fail-fast",
            ["<step> [module ...]"], lambda a: 2, passthrough=True, examples=["build", "test api"])
