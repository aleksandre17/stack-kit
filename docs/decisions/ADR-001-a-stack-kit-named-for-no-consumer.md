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

## Amendment 1 — K1 as built (2026-10-15, owner-delegated)

**Landed.** Every name is declared once in `lib/identity.json` (current and `legacy*`, with
`legacyRemovedIn: 2.0.0`); Python (`lib/identity.py`), bash (`lib/project.sh`) and PowerShell
(`lib/project.ps1`) project it. The tree was renamed mechanically (197 files, 11 paths); the
former command paths remain as shims that read the declaration. `stack-kit migrate` carries a host
across. Proof: `tests/test_identity.py` — the boundary (no tracked file names the former kit outside
the declaration, this record and the changelog; mutation-checked), a host DERIVED from the reference
consumer by turning every declared rename back resolves to the same root under Python, bash and
PowerShell and is told each replacement once, the former command runs, the migration moves what the
kit owns and prints what the host wrote, and two manifest homes are refused.

**Decided while building, with what was rejected:**

1. **One prefix rule for every variable** (`GEOSTAT_X` → `STACK_KIT_X`), so `STACK_KIT_KIT_ROOT` is
   awkward and stays. *Rejected:* a per-variable rename table — a second rule each runtime would have to
   carry, for one prettier name.
2. **Former variables are adopted inward, never mirrored outward.** At load, each runtime copies a former
   variable to its current name (the current one wins), tells it once, and unsets the former so a child
   is not told again. *Rejected:* exporting both names to every child — it doubles every export for the
   whole 1.x line, and no host reads a kit-set variable (the two known hosts were searched; their
   launchers SET the former names, which inward adoption serves).
3. **"Once" is per process tree, carried in `STACK_KIT_NOTICED`.** *Rejected:* a per-process memo — a
   bash `$(…)` subshell cannot export to its parent, so every resolution re-told the same name.
4. **The migration is part of `migrate`, not a new verb**, and it never rewrites the host's own files:
   it prints each line with its replacement. *Rejected:* rewriting host launchers and docs in place — a
   host's words are its owner's decision (the agent kit's relocation rule, ADR-021).
5. **The reference consumer is on the current names**; the legacy host is derived from it in each run.
   *Rejected:* a second, tracked legacy fixture — two specimens drift, and the derived one follows the
   declaration under test.
6. **Consumer-shaped defaults went with the name**: the java-boot check's integration keys became
   `modules.<id>.check.{requiredEnv,optionalEnv}`; `primary_api_module_id` lost its privileged ids for
   `stack.primaryApiModule` or role `api`; generated Spring defaults use `app`.

**Owed, named:** `config/config-catalog.json` `envProfileSecretsBlock` still renders one consumer's AI
integration keys into every env-profiles module (K5, with the catalogue's sensitivity columns); several
unit tests still use `chat-api` as sample module-id data (K3, with the test split).

## Amendment 2 — K2 as built (2026-10-15, owner-delegated)

**Landed.** `lib/resolution.py` is the one resolver; `lib/resolve_cli.py` is how a shell asks it.
The seven shell libraries keep every public function and hold no rule. Proof:
`tests/test_resolver_parity.py` asks bash, PowerShell and Python 22 questions on a host bent to
exercise each rule that had drifted, and compares the answers; no shim spells a manifest field
(the sensor is checked on specimens). Both are mutation-checked: a spelled field in `project.sh`,
and first-wins in the env value, each turn the suite red. The divergences found and settled are
listed in the changelog.

**Decided while building, with what was rejected:**

1. **One flat context map, identical in every runtime** (`kind:key` → text): bash holds it as one
   associative array, PowerShell as one hashtable, so parity is a comparison of two maps.
   *Rejected:* per-function Python calls from the shells (the bash status quo, one interpreter
   start per field read), and a nested document each shell walks (the walk is a rule).
2. **Cache what the manifest says; ask for what the environment says.** The context is resolved
   once per declared root (else working directory) for a shell's lifetime; env files, deploy values,
   slugs and paths are asked each time, because an env file is written or a variable exported
   during a run. Secret values never enter the cached context. *Rejected:* caching the environment's
   answers too — stale within the run that changes them.
3. **The declared root is authoritative, and the search starts at the working directory.**
   *Rejected:* PowerShell's search from the kit's own folder — a kit checked out inside another
   repository resolves that repository from anywhere, silently.
4. **Convention defaults are a declared list**, not "any field of the template": the template also
   carries sample modules, aliases and stores.
5. **Compose semantics for env values** (a later file wins), and **the operator's process
   environment before `deploy.env`** (an explicit override beats a file).
6. **No invented remote path.** With neither an explicit path nor a server to derive one from, the
   deploy base and the infra deploy path are refused.
7. **Paths reach Git Bash as Git Bash spells them** (`/c/...`): the resolver respells paths when
   asked with `--shell bash` on Windows, because a drive colon handed to `scp` or `rsync` reads as a
   host name. **Output is LF, UTF-8**: a CR would ride inside every value a shell reads.

**Owed, named:** `lib/module-manifest.ps1` (typed PowerShell accessors for `hybrid.*`, `spring.*`)
still names fields, by design one file of them; it moves with the module facts into the context
when a driver needs them in bash too. `lib/driver_api.py` and `lib/modules_cli.py` remain separate
CLIs over the same Python and fold into `resolve_cli.py` with K3's tree.
