---
kind: decision
authority: canonical
owns: identity-and-shape
---

# ADR-001 — A stack kit named for no consumer, with one resolver, in the agent kit's handwriting

- **Status:** Accepted (2026-10-15; owner-delegated, as for the agent kit's ADR-015 amendment 5). The
  owner's instruction: *the kits are frameworks — one structure, one pattern, one handwriting for every
  project; complete, organised, powerful tools at the level of modern engineering; look at them from the
  outside and never obey them.*
- **Sources, measured 2026-10-15 at `4db8fad`:** the tree (356 files), `ARCHITECTURE.md`, `README.md`,
  `docs/*.md` (15 guides), `lib/`, `cli/`, `drivers/registry.json`, `CHANGELOG.md`; the second host's
  ADR-0003 rows 15–17 and its stack-kit proposals S1–S6; the prior system's `ops/` (`RUNBOOK.md`, the
  `validate:local` pipeline, `compose/catalog.json`, `config/README.md`).

## What was measured

1. **The framework is named after one of its consumers.** The repository is `stack-kit`, and inside it
   **251 of 356 files name `geostat` 1,582 times**: the package (`geostat-kit`), the command (`geostat …`),
   the manifest (`geostat.ops.json`), the environment (`GEOSTAT_PROJECT_ROOT` ×95, `GEOSTAT_KIT_ROOT` ×70,
   `GEOSTAT_MODULE_ID` ×61 …), even one consumer's own credential (`GEOSTAT_SEARCH_API_KEY`). The kit's
   own maturity check #1 — *no consumer brands in runtime* — exempts the one brand it carries everywhere.
2. **One resolution, three homes.** Reading the manifest and resolving a module is implemented in
   Python (`lib/project_context.py`, 205 lines), Bash (`lib/project.sh`, 321) and PowerShell
   (`lib/project.ps1`, 362), with the same split for env, modules and drivers. Three implementations of
   one rule agree only by discipline; the first fix applied to two of them is a divergence nobody sees.
3. **No decisions.** Fifteen guides (`ADOPT`, `ADOPTION`, `ADOPTION-LINE`, `INSTALL`, `STARTER`,
   `PACKAGE`, `PACKAGE-ARCHITECTURE`, `PACKAGE-PRINCIPLES` …) restate one another, and no decision record
   says why anything is the way it is.
4. **Proposals owed by the second host** (its ADR-0003): S1 the product/ops tree as a declared layout
   with a floor gate; S2 container delivery for `dotnet-aspnet`; S3 a sensitivity/owner/rotation catalogue
   for configuration; S4 the remaining driver ladders; S5 tests that rewrite tracked fixtures; S6 a
   project-local driver registry.
5. **What the prior system's `ops/` proved works** and the kit does not carry: a single `validate` that
   runs fail-fast STAGES against a real stack and ends on VALUE ANCHORS (a row count, a known value), so a
   green means the real path works; schema migrations kept STRUCTURE-ONLY with demo data loaded through the
   same pipeline production uses; the secrets a human must supply named before any deploy.

## Decision

1. **The kit names no consumer.** Package `stack-kit`; command `stack-kit`; manifest `stack-kit.json`;
   environment `STACK_KIT_*`. (A bare `stack` is refused: it collides with an existing build tool's binary.)
   Expand–contract: for the 1.x line the old manifest name, command and variables are READ, each read
   printing one deprecation line naming its replacement; 2.0 removes them. A boundary test fails on any
   consumer name in the kit outside the deprecation shims and the migration notes, and the consumer's own
   credential leaves the kit.
2. **One resolver.** Python is the only implementation of manifest reading, module resolution, env
   composition and driver lookup. `lib/project.sh` and `lib/project.ps1` become thin shims that call
   `lib/resolve_cli.py` and export what it prints; they hold no rule. A test asserts the shims carry no
   resolution logic of their own (no manifest field is spelled in them).
3. **The agent kit's handwriting.** `docs/decisions/` holds the decisions; the fifteen guides reduce to
   `INSTALL`, `ADOPT`, `REFERENCE` (the manifest and the tree) and `GOLDEN-PATHS`, each kind declared;
   `CHANGELOG.md` per release; tests split `unit/` and `acceptance/` with the parallel runner; the product
   and ops tree is a DECLARED LAYOUT (`path`, `holds`, `writer`, `read_when`, `lifecycle` — the records-map
   row) held by `stack-kit validate` as a floor gate (owed S1).
4. **`validate` is a pipeline of declared stages ending on anchors.** A manifest declares `validate.stages`
   (infra up · migrate from scratch · build · tests against the live stack · service health · ingest through
   the production path · VALUE ANCHORS · teardown); every stage is fail-fast and tears down on failure; a
   stage list with no anchor is refused, because a pipeline that never compares a value proves only that it
   ran. Migrations are structure-only; demo data is loaded by the ingest stage, never by a migration.
5. **Configuration carries its sensitivity.** `config-catalog.json` gains, per key, `sensitivity`, `owner`,
   `allowed_source` and `rotation` (owed S3); `validate` refuses a secret-class key with a committed value.
6. **Delivery ladders by declaration** (owed S2, S4): `dotnet-aspnet` container delivery, `node-vite`
   delivery and the hybrid rungs, each declared in the driver registry and refused by name where undeclared.
7. **A test never rewrites a tracked file; a project may declare its own drivers** (owed S5, S6): fixtures
   are copied to a temporary tree before any write, and the driver registry composes the kit's with a
   project-local `drivers/registry.json`, an id collision refused.

## Order of slices

| Slice | Lands | Proof |
|---|---|---|
| K1 | identity: names, env, manifest file, command; deprecation reads; boundary test; the consumer credential out | boundary test green; a host on the old names still runs and is told the replacement once per name |
| K2 | one resolver: shims over `resolve_cli.py` | the shim test; the PowerShell and Bash entry points resolve identically to Python on the golden fixture |
| K3 | handwriting: decisions, guides reduced, tests split, parallel runner, declared tree + floor gate | the floor gate fails a missing declared place and names an undeclared one |
| K4 | `validate.stages` with anchors; structure-only migrations | a stage list without an anchor is refused; a failing stage tears down and exits non-zero |
| K5 | configuration catalogue with sensitivity | a secret-class key with a committed value is refused |
| K6 | delivery ladders (`dotnet-aspnet` container, `node-vite`, hybrid) | each declared rung runs on the fixture; an undeclared one is refused by name |
| K7 | fixtures never rewritten; project-local drivers | a test run leaves `git status` clean; a project driver is found and an id collision refused |

## Rejected alternatives

- **Keep `geostat` as the brand "because the repository already works".** The cost of change is never an
  argument (Cardinal I); a framework named after one consumer tells every other consumer it is somebody
  else's tool, and its own boundary rule cannot be enforced while it carries the exception.
- **Rename in one break with no reading of the old names.** Two hosts run on the old names today; a rename
  that strands them is a migration nobody can replay. Expand–contract costs one deprecation line per name.
- **Keep three resolvers and test that they agree.** A test asserting that copies agree is the smell that
  they should be one (construction over convention); the shells keep their place as shims.
- **Rewrite the kit in one language including the scripts.** The shell and PowerShell entry points are what
  operators type on two platforms; they stay, holding no rule.
