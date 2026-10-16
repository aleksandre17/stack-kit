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

## Amendment 3 — K3 and K4 as built (2026-10-15, owner-delegated)

**K3 landed.** `docs/` holds `decisions/` and the four guides, each declaring `kind: guide` and what
it `owns`; twelve guides were folded in and deleted, with every unique still-true fact kept and each
fact the code contradicted dropped (held by `tests/unit/test_handwriting.py`, including every
relative link). Tests are split `unit/` (in-process, 1.4 s) and `acceptance/` (shells and CLIs,
14 s). The host tree is a declared layout held by `validate` as a floor (`lib/layout_floor.py`,
the agent kit's row shape over disjoint places; `tests/acceptance/test_layout_floor.py`).
`.gitattributes` pins LF.

**K4 landed.** `validate.stages` (`lib/pipeline.py`) and structure-only migrations
(`lib/migrations_gate.py`, each driver declaring its migration files and data patterns), proved by
`tests/acceptance/test_pipeline.py` and `tests/unit/test_migrations_gate.py`.

**Decided while building, with what was rejected:**

1. **No parallel runner.** The suite takes 18 s. *Rejected:* porting the agent kit's runner, which
   exists because its suite took 28 minutes; matching the handwriting is not a reason to carry a
   tool with nothing to do.
2. **Derived rows only from what the manifest DECLARES**, never from a default the host never
   wrote. *Rejected:* requiring every convention place; a host that uses no compose would fail for
   lacking a catalog.
3. **The schema is interpreted by the kit on every machine** (`lib/schema_check.py`, the agent
   kit's subset plus `oneOf`, schema-valued `additionalProperties` and `default`). *Rejected:*
   keeping `jsonschema` optional (found: on a host without it the whole schema was decoration),
   and requiring it (an install the host must do before the kit can judge).
4. **Plain `validate` refuses an unprovable stage list; only `validate --stages` runs it.**
   *Rejected:* running the stack on every `validate`, which developers run constantly.
5. **The technology of migrations is the driver's declaration.** *Rejected:* SQL patterns in the
   gate, which would name one technology and miss the next driver's.
6. **Launchers declare a simple param block.** Found while reducing the guides: an advanced block
   adds PowerShell's common parameters, and `-d` bound to `-Debug` before the CLI saw it.
   `tests/unit/test_handwriting.py` holds every launcher the kit ships.

**Owed, named:** the CLI help omits `--mode remote`; `toolkit/deploy/deploy-path.sh` defaults
`stack.deployBaseSecretsModule` to a literal module id; `manifest.schema.json` still carries
consumer-shaped fields (`ci.rag*`, `modules.*.catalog`, `modules.*.derivation`), each to be
generalized or removed with a deprecation read.

## Amendment 4 — K5 as built (2026-10-15, owner-delegated)

**Landed.** The key catalogue's shape is the kit's (`config/config-keys.schema.json`) and the host's
catalogue is named by the manifest (`config.keys`); `lib/config_keys.py` holds it in `validate`.
Proof: `tests/unit/test_config_keys.py`, where a SECRET committed in JSON, YAML or an env line is
refused and no verdict carries the value. On the second host, before any change there, the gate
named exactly the exposures that host had already registered by hand (its AIR-001), and nothing else.

**Decided while building, with what was rejected:**

1. **The catalogue is the host's file, its shape the kit's.** The second host had already invented
   one (key, sensitivity, owner, allowed source); the kit adopted that shape and added `rotation`.
   *Rejected:* growing `config/config-catalog.json`, which holds Spring templates, not keys.
2. **A known exposure is printed, not failed.** *Rejected:* failing until removal. Rotation is an
   operator's act outside the repository, so the gate would stay red on work no commit can do, and
   a gate that is always red is a gate nobody reads. Silence was rejected too: an exposure is named
   on every run until the work it cites removes it.
3. **References are not values.** `${NAME}` and `${NAME:default}` point at the environment.
   *Rejected:* flagging a reference's default, which is a development fallback the generators write
   on purpose. A secret's default is refused where it is declared, in the catalogue.
4. **The generated profiles carry no integration.** The block one consumer needed moved to that
   module's declaration (`configGen.profileYml`); the reference consumer declares it, and its golden
   output changed only by the consumer's AI and package loggers leaving the kit's template.

## Amendment 5 — K6 and K7b as built (2026-10-15, owner-delegated)

**K7b landed.** `drivers.registry` names a project registry, composed with the kit's in
`lib/modules.py` (each driver at `<registry dir>/<id>/`); an id the kit already has is refused
(`tests/acceptance/test_project_drivers.py`).

**K6 landed.** Every driver declares its delivery ladder and the CLI names none
(`tests/acceptance/test_delivery.py`: every built kit rung is planned through the real CLI to a
script its driver declares; rungs run through a project driver, binding operands by name and order,
under bash or PowerShell by script; undeclared and pending rungs refused; mutation-checked).

**Decided while building, with what was rejected:**

1. **The dotnet container rung is declared pending, not built.** This workstation has no docker,
   and a Dockerfile and compose wiring nobody has run is a claim, not delivery. *Rejected:* shipping
   it untested. The pending rung is refused with its reason until a docker host proves it.
2. **A rung is a driver command with arguments, or a kit verb.** *Rejected:* a rung kind per
   technology, which would move the driver-name ladder from the CLI into the rung grammar.
3. **The script decides how it is run, not the driver.** `java-boot` declares `runtime: bash` and
   ships a PowerShell `run`; the CLI had special-cased `run` for exactly that. Dispatch by script
   type removes the case. *Rejected:* a per-command runtime field, a second home for what the file
   name already says.
4. **Operands bind to the parameters a script declares.** This replaces one driver's hand-written
   `-Environment` parser in the CLI. *Rejected:* keeping per-driver argument shapes in the CLI.
5. **`release` absorbs `deployArgs`.** *Rejected:* keeping both, which would be two homes for one
   argv; a project registry on the old field is still read.

**ADR-001 slices: K1–K7 landed.** Still owed (named in the amendments above): the container rung;
`--mode remote` in the CLI help; a literal default module id in `toolkit/deploy/deploy-path.sh`;
consumer-shaped schema fields (`ci.rag*`, `modules.*.catalog`, `modules.*.derivation`); folding
`driver_api.py` and `modules_cli.py` into `resolve_cli.py`; `lib/module-manifest.ps1`'s typed
accessors.

## Amendment 6 — the host run, as the second host found it (2026-10-16, owner-delegated)

Taking geostat_in_out onto the renamed kit showed that K6 had kept its promise for the CLI and not
for the host run: `toolkit/hybrid/Invoke-HybridRun.ps1` still branched on three driver names and
parsed env files itself, in an order (`.env.prod`, then `.env.dev` over it) that `lib/envfile.py`
did not know.

1. **Every driver declares its launch step.** The three branches moved verbatim into
   `drivers/<id>/ps1/hybrid.ps1`; the runner joins the guarded list in
   `test_declared_agnosticism.py`, and a `hybrid` rung without a declared step fails
   `test_registry_integrity.py`. *Rejected:* leaving the three as "legacy rungs", which is how a
   ladder survives a decision that removed it.
2. **The host-run order is a rule in the one home.** `envfile.HOST_RUN` = prod, then dev: a host
   run is a development run, and the production file only fills what development leaves unset.
   *Rejected:* the compose order (dev, prod), which would run a developer's process on production
   values whenever both files set a key.
3. **`hybrid boot` calls the runner, not the driver's `run`.** Every driver's `run.ps1` is the same
   delegate; routing through it made a project driver need a `run` command to be host-run.
4. **A declared host file is a floor row.** `config.keys` and `vscode.cliScript` join the derived
   rows: a manifest naming a file that is not there is a broken manifest.

Proof: `tests/acceptance/test_delivery.py` runs a project driver's hybrid rung through the real CLI
and reads `.env.dev` over `.env.prod` from the process; `tests/unit/test_envfile.py`;
`tests/acceptance/test_layout_floor.py`. The order was mutation-checked (reversing `HOST_RUN` fails
both). Still owed: the four identical `run.ps1` delegates.

## Amendment 7 — the owed list, closed (2026-10-16, owner-delegated)

Everything the amendments above named as owed, except the container rung, which still has no docker
host to be proven on.

1. **The schema spells no consumer.** `ci` lost fourteen script fields one former consumer's tools
   ran (`ragSmoke`, `ragEval*`, `chatCatalogRagSmoke`, …) and that no line of the kit ever read;
   `modules.<id>` lost `catalog` and `derivation`, the same. A host's further CI scripts are
   `ci.scripts` (name → path), and every one is checked to exist and held as a layout-floor row, like
   the four the kit runs (`manifest_defaults.declared_ci_scripts`, the one list). A module's own
   configuration for its own tools is `modules.<id>.extensions`, which the kit reads nothing of; the
   module schema is now closed (`additionalProperties: false`), so a misspelt field is refused instead
   of ignored. `migrate` carries the former keys to the new homes under the same names, and refuses
   to overwrite a key already there; `validate` names that door. *Rejected:* keeping the fields as
   deprecated (the kit would go on carrying one consumer's vocabulary); an open module object (a
   misspelling passes); dropping the keys (a host's data, lost by the kit).
2. **The host run has one home.** The four `run.ps1` delegates are gone. A driver that declares its
   launch step (`hybrid.script`) is given `run` = `toolkit/hybrid/Invoke-HybridRun.ps1` by
   `lib/modules.driver_commands`, the one place a driver's commands are resolved (the resolver's
   context, the CLI dispatch and `dev up` all read it). The runner takes its module from the dispatch
   (`STACK_KIT_MODULE_ID`) when not given one. A kit driver declaring its own `run` beside a launch
   step fails `test_registry_integrity.py`; a project driver's own `run` is still its own.
   *Rejected:* a `{via}` form for commands (a second grammar beside the delivery ladder's for one
   fact); one shared script reached by a `../` path from each driver (four declarations of one thing).
3. **The stack deploy names no driver.** `toolkit/deploy/stack-remote.sh` appended the environment
   flag and its own options only to `java-boot`, and called a consumer's `tools/stack-kit.ps1`. The
   environment is now the release rung's argument (`--{environment}`), and the options a rung passes
   on are declared there (`forwards`); `node-api`, which accepts both and was given neither, now
   deploys the environment asked for. The runner calls the kit's own CLI, under `pwsh` when present.
4. **One command line for the resolver.** `lib/driver_api.py` and `lib/modules_cli.py` folded into
   `lib/resolve_cli.py` (`driver-types`, `driver-command`, `stack-steps`, `stack-health`,
   `stack-endpoints`, `compose-names`, `compose-service`); their duplicate manifest and registry
   readers, and two verbs printing one plan (`stack-steps`, `stack-deploy-steps`), went with them.
   Roles, types and aliases were already the context's.
5. **The kit keeps no list of a driver's fields.** `lib/module-manifest.ps1` named `hybrid.*`,
   `spring.*` and Flyway fields for every runtime, four of them read by nothing. A driver now reads
   its own fields by name (`Get-ModuleField <id> <path>[, <path>]`, `lib/drivers.ps1`); the JAR boot
   moved from `toolkit/hybrid/` into the driver that is its only user (`drivers/java-boot/ps1/_jar-boot.ps1`).
6. **No literal folder.** The deploy-base secrets folder defaulted to `backend` in bash and PowerShell;
   it is now `stack.deployBaseSecretsModule`, else the primary API module's folder, else none — one
   rule in the resolver's context (`deployBaseSecretsFolder`). The Python `deploy_path_summary`, read
   by no runtime and carrying `/home/administrator` and `backend` literals, was deleted.
7. **UTF-8 at the Python boundary.** Both shims that start a kit script (`Invoke-StackKitPythonExe`,
   `stack_kit_python`) set `PYTHONUTF8=1` for the child only; a script writing to a pipe on Windows
   otherwise encoded in the ANSI code page and an em dash arrived as `�`.
8. **Every in-place page's links resolve.** Driver, toolkit and CI READMEs linked a former consumer's
   `docs/`; they point at the kit's guides, and `test_handwriting.py` now holds every `.md` under
   `drivers/`, `toolkit/`, `ci/`, `adapters/`, `compose/`, `contracts/`, `lib/`. (The compose catalog
   path the guides state, `ops/compose/catalog.json`, was already the code's.) The CLI help names
   `--mode remote`, `deliver`, and that a module's commands are its driver's.

Proof: `tests/unit/test_migrate_manifest.py`; `tests/unit/test_validate_manifest.py` (the former
shape refused, with the door); `tests/acceptance/test_layout_floor.py` (`ci.scripts` rows);
`tests/acceptance/test_driver_resolution.py` (`run` is the host runner; stack steps' environment and
`forwards`); `tests/acceptance/test_delivery.py` (`mod <id> run` runs the runner through the real CLI);
`tests/unit/test_backend_deploy_paths.py` (deploy-base folder); `test_declared_agnosticism.py` guards
five more generic files. Each new test was mutation-checked. **Still owed:** the container rung; the
remote Windows/IIS delivery path; `toolkit/deploy/` layout-migration and marker scripts that still
name `java-boot`, `node-vite` or a `backend` folder (one consumer's server history, run by hand).

## Amendment 8 — a new project works with no setup of its own (2026-10-16, owner-delegated)

The owner asked that the kits be judged against current international practice rather than their
own rules: a new project must get a working system with no per-project setup. An external audit's
findings, each verified in code first:

1. **Every module builds, tests and lints through its driver.** `dotnet-aspnet` declares
   `build`/`test`/`lint` (`dotnet build|test` of `dotnet.solution`/`dotnet.test`, else the project;
   `dotnet format --verify-no-changes`); `java-boot` declares `build` (`-x test`) and `test` through
   the module's Gradle wrapper (`ps1/_gradle.ps1`, shared with its launch step). A Node-family driver
   declares `packageScripts` (step → package.json script) and is given `build`, `test`, `lint` = the
   kit's one runner, `toolkit/node/Invoke-PackageScript.ps1` (package manager from the nearest
   lockfile, install from it when `node_modules` is absent). `stack-kit build|test|lint [module]`
   runs a step across the modules, fail-fast, each in its own process so its exit code is the step's.
   `lint` is optional (`OPTIONAL_STEPS`): skipped and said where absent; a missing `build` or `test`
   fails. *Rejected:* argv templates in the registry (a substitution grammar for every toolchain's
   flags); a per-driver copy of the Node runner (three homes for one rule); one process for all
   steps (a step's `exit` would end the run, and an exit code would be lost).
2. **One cross-tool contract: `commands`.** A top-level block of literal command lines (`test`
   required; `build`, `lint`, `run` optional; strings only); the agent kit's detector reads
   `commands.test` and `commands.build`. The scaffold writes them through the host launcher
   (`pwsh ops/cli/stack-kit.ps1 test`); `validate` refuses a line naming a script that is not there.
   *Rejected:* argv arrays (the contract is a line any tool runs verbatim); deriving the lines at
   read time (another tool cannot run the kit to find out what to run).
3. **`node-spa`: any SPA by its own scripts.** Angular CLI, Vite, React or Vue: `build`/`test`/
   `lint`/`start` are the package's, renamed per module in `node.scripts`; `run` is the `start`
   script with the module's development configuration. Its release rung is pending: the output
   directory is the framework's and has to be declared and proven. *Rejected:* generalising
   `node-vite` (its remote dev and static deploy are Vite-shaped and serve a host already).
4. **A run on this machine reads one environment (12-factor III).** `envfile.run_files`: the
   folder's shared, non-secret `.env`, then `.env.dev`; `.env.prod` only with `--env prod`
   (`hybrid boot --env prod`, `deliver hybrid --env prod`). This reverses amendment 6's "dev wins,
   prod fills", which let a development run read production values and secrets. The old layout's
   migration is named, never performed: `validate` and `migrate` list, per secrets folder, the keys
   a development run no longer reads from `.env.prod`, by name and never by value. *Rejected:*
   copying them into `.env.dev` (`migrate --apply` would itself carry production secrets into a
   development file).
5. **CI is generated from the manifest.** `stack-kit ci-gen [--force|--check]` writes
   `.github/workflows/ci.yml`: a job per module, the toolchain its driver declares (`ci.setup`, the
   version from `toolchain.version`), then its lifecycle steps through the launcher, `permissions:
   contents: read`, one run per ref. Every action is pinned by full commit SHA in
   `lib/ci-actions.json`; each of the four was read with `git ls-remote` on 2026-10-16 (lightweight
   tags: the SHA is the commit). `init` generates it. *Rejected:* a hand-written template (it drifts
   from the modules the day one is added); tag pins (a tag can be moved).
6. **The quick start is true.** `init` failed at its first Python call (`& @py`, an array spliced as
   one command name) and then at `Get-ManifestField`, which it never loaded; the manifest it
   scaffolded failed its own `validate` (an nginx template it did not ship, module env examples in
   `apps/` where the kit reads `ops/config/<module>/`). All fixed, and held by
   `tests/acceptance/test_init.py` (empty repository → `init` → `validate` passes, `commands`
   present, CI current, secrets ignored and examples tracked). README: a quick start, the real
   remote, no BOM; the license is pending (the owner's choice). `vendorDirs` gains
   `platform/kits/stack-kit`. PowerShell: 7+ on any OS, and Windows PowerShell 5.1 on Windows, now
   true because every non-ASCII script carries a BOM (5.1 read them as ANSI); no other text file may
   start with one (a BOM broke three shebangs).
7. **A run record.** Every `deliver` rung and lifecycle step appends one JSON line (kind, step,
   module, environment, start, end, duration, exit, git SHA, dirty) to `.stack-kit/runs/runs.jsonl`,
   a directory that ignores itself: enough to compute DORA's four keys. A record that cannot be
   written is said and never fails the step. The `toolkit/deploy/` layout migrations and markers no
   longer name `java-boot`, `node-vite` or a `backend` folder: they find their module by the deploy
   kind its driver declares (`deployKind:<kind>`).

Proof: `tests/acceptance/test_lifecycle.py` (real `npm run`, a stand-in Gradle wrapper, a real
`dotnet build`; fail-fast exit code; run records), `tests/acceptance/test_init.py`,
`tests/acceptance/test_delivery.py` (one environment per run), `tests/unit/test_envfile.py`,
`tests/unit/test_ci_gen.py`, `tests/unit/test_validate_manifest.py` (`commands`),
`tests/unit/test_handwriting.py` (byte order marks). Each new test was mutation-checked. **Still
owed:** the container rung; remote Windows/IIS delivery; `node-spa` release; the generated workflow
has not yet run on GitHub's runners (pwsh on Linux reading the kit's backslash paths is unproven).

## Amendment 9 — where a deploy goes is declared; the kit holds no server (2026-10-16, owner-delegated)

The owner's point, verified in code: the server, the ssh settings and the remote directories were
values the kit held or guessed (`/home/<user>` from `DEPLOY_SERVER`, a `/home/deploy` fallback, a
fixed remote tree, `StrictHostKeyChecking=accept-new` in the scaffold), and lived only in a
gitignored `deploy.env`: one server per repository, no named environments, nothing reviewable. A
second host, gesotat-system, keeps a hand-written deploy script hardcoding its server and tree --
what a host must never need again. The design follows the field (Kamal's deploy.yml, Capistrano's
stages, an Ansible inventory), as a desired-state cycle: declare, validate, plan, apply, verify.

1. **Declared targets.** The manifest names a tracked, non-secret file (`deploy.targets`, schema
   `config/deploy-targets.schema.json`); a gitignored `<name>.local.json` beside it is merged over it
   per machine. A target is `host`, `user`, `port`, an absolute `root`, a `runtime` (`docker-compose`,
   `static`, `iis` -- the Windows/IIS case has its place while its delivery stays pending), `ssh`
   (`identity`: `agent` | `env:VAR` | `file:<ignored path>`, a reference never a key; `knownHosts`;
   `hostKeys` `pinned` | `accept-new`), a `layout`, `ports`, `keep`, or `pending` with its reason.
   `--target <name>` selects one, else `defaults.<environment>`. A value set by the flag never
   outlives the run (a launcher run in the operator's session would otherwise deploy the next
   command to the last one's target). The file lives in `ops/deploy/`, beside `ops/config/`, not under
   it: the secrets tree ignores what it does not whitelist, and a targets file is tracked by design.
2. **One home.** The resolver answers every server, ssh and remote-path question from the selected
   target: `DEPLOY_SERVER`, `DEPLOY_SERVER_BASE` and a folder's `DEPLOY_PATH` asked of it are the
   target's, `ssh-args` (`-o Port`, `StrictHostKeyChecking=yes` against the pinned file, the identity
   reference, `-F`, options; one list for ssh, scp and rsync through `RSYNC_RSH`), `remote-path`.
   The bash and PowerShell shims only ask it; the bash copy of the path rules is gone. *Rejected:*
   per-script target reading (thirty-five files, thirty-five homes).
3. **The layout is the owner's tree, as one default template** (`config/deploy-layout.default.json`):
   one root; one directory per project under it; inside, one disjoint tree per environment
   (`{root}/{project}/{environment}/`), each with `modules/{service}/` (the service's unit: `logs`,
   and declared ahead `releases`, `current`, `runtime`), `stack/` (stack config: `env/{service}.env`)
   and `infra/`; `dev/modules/{service}/workspace` for remote dev. A target overrides any template.
4. **Isolation is a guarantee, enforced in the resolver.** (a) Every rendered path is normalised and
   refused unless it lies under `{root}/{project}/`, and the project directory under the root:
   `validate` refuses a layout that escapes, and every deploy's `remote-path` does too. (b) Before a
   deploy writes anything it runs `remote-preflight` on the server: it writes
   `{root}/{project}/.stack-kit-project` (slug and repository, the origin as host/path) or refuses a
   directory another project owns, naming both. (c) Compose runs as `-p {project}-{environment}`;
   declared host ports are unique per host across every target and environment (`validate`), and the
   preflight refuses one another compose project publishes, naming it. (d) A remove or prune is
   refused outside the project's directory (`confined`), and `node-vite`'s staging moved from the
   server-wide `{base}/deploy-staging` into the module's own directory. Layout migration and scoped
   cleanup -- tools for the old trees -- refuse a host with targets.
5. **Verify.** `targets --verify` reads what is under `{root}/{project}/` over ssh, read-only, and
   reports drift against the declared tree: an undeclared path (reported, never deleted), a missing
   declared one, an absent or foreign marker, more releases or versioned artifacts than `keep`, a
   `current` that points at nothing. Exit 1 on drift; 2 when nothing could be verified (pending,
   unreachable, no ssh client) -- never a pass by default.
6. **Runtime config is declared and never secret.** `modules.<id>.runtimeConfig[]`
   `{from, to, environments}`: `to` stays inside the unit's `runtime/`; a structured `from` (JSON,
   YAML, env) may carry no catalogued SECRET value, and any other (env.js, nginx.conf) may not even
   name one, whether tracked or not (`config.keys`).
7. **Provenance.** Every java-boot and node-api deploy carries `IMAGE_REVISION` (the caller's, else
   `git describe --tags --always --dirty`) into compose, and a production deploy from a checkout with
   uncommitted or untracked files is refused (`toolkit/deploy/provenance.sh`) -- the one thing
   gesotat-system's script did that the kit's java-boot delivery did not.
8. **Migration.** A host on `deploy.env` keeps working, read until 2.0.0, and `validate` names each
   deprecated key. `migrate --apply` declares its server, base and ssh settings as a target in
   `ops/deploy/targets.json`. A root it once inferred is written as what it was, and said; a value
   that looks like a key or a password is refused, never written; `StrictHostKeyChecking=accept-new`
   becomes the declared `hostKeys: accept-new`. The scaffold ships `ops/deploy/` (one `pending` target,
   a `known_hosts` to fill, a README) and no longer suggests trust on first use.

*Rejected:* inferring nothing at once on the deprecated path (working hosts would break mid-migration;
the inference is kept only there, named, and gone at 2.0.0); a per-folder absolute `paths` override
(it could point anywhere, so isolation would be a convention again); an ownership check by slug alone
(two repositories that choose one slug would share a directory).

**Declared ahead, pending, and why:** the docker-side delivery of the tree -- a release per version
with a `current` pointer (rollback by re-pointing, replacing `versions/`), one `stack/` compose per
environment with `stack/env/`, runtime-config upload and read-only mount, and container, network and
volume names namespaced by the compose project. Each changes the contract between the generated
compose file and the running containers, and is proven only against a docker host, as the container
rung is. Until then each unit holds the driver's current anatomy (compose file, env file, artifact,
`logs/`, `versions/`), which already gives the environment split and per-project isolation of files.

Proof: `tests/unit/test_targets.py` (declaration, selection, layout, escape refused everywhere,
ports, ssh, migration, runtime config), `tests/acceptance/test_targets_shells.py` (bash and
PowerShell through the resolver; the flag does not outlive its run; provenance),
`tests/acceptance/test_targets_remote.py` (a local directory stands in for the server, with stand-in
`docker` and `ssh` on PATH: the marker claims or refuses, a foreign port is refused, `--verify` reports
each kind of drift and exits 1, and 2 when pending or unreachable). **Not proven against a real
server:** sshd, docker's compose-project port labels, `find` on busybox. A dangling-`current` check
is written and its test skips where the machine cannot create a symlink (this one).

## Amendment 10 — the manifest is drafted from the tree, by declaration (2026-10-16, owner-delegated)

The owner: ten projects must stand on one architecture and structure, and nothing true of all of them
may be written by hand in each. A host's manifest was hand-written.

1. **Evidence is a driver's declaration.** Each registry entry declares `detect`: `all` conditions on
   a directory's own files (`{file, matches}`, `{any: [...]}`, `{none}`) and `reads` (what it takes
   from the evidence: `{name}` -- a matched file's name; `{find, matches, mentions}` -- a repository
   file whose content matches and mentions an earlier read, as a path from the module). Declared:
   `dotnet-aspnet` (a `*.csproj` on `Microsoft.NET.Sdk.Web`; reads its project, and the test project
   that references it), `java-boot` (a Gradle build applying `org.springframework.boot`, itself or one
   level down -- a multi-project build is one module), `node-spa` (`package.json` + `angular.json`),
   `node-vite` (`package.json` + a `vite.config`), `node-api` (`package.json` depending on a server
   framework, and neither of the other two). `lib/draft.py` evaluates declarations and names no
   ecosystem; a project's own driver (K7b) declares its evidence the same way.
2. **The draft proposes; the host's declarations win.** `init --plan` prints, against the current
   manifest, only what is absent: modules (type, role, path, secretsModule, the driver's reads),
   aliases, `commands`, `layout.profile`. A drafted module is the existing module at the same path,
   whatever its id; it gains only absent fields. `init --approve <who>` writes it and records
   `draft.approvedBy`/`approvedAt`. A directory two drivers claim is refused, naming both; the
   outermost claim wins; the vendored kit, build output, dependencies and nested hosts are never
   evidence.
3. **The canonical tree is declared once.** `config/layout-profiles/monorepo.json` (`platform/apps/`,
   `platform/kits/`, `ops/cli/`, `ops/config/`, `docs/`); a manifest naming `layout.profile` has those
   places as derived floor rows, and `layout.entries` keeps only the host's own.

*Rejected:* detection in code per ecosystem (a second home for what a driver is); a draft that
rewrites the manifest (a host's choice -- `launchProfile`, `publishExpect`, its secrets root -- is not
evidence and would be lost); guessing between two claiming drivers.

Proof: `tests/unit/test_draft.py` -- a geostat-shaped tree (ASP.NET Core + its test project + Angular
under `platform/apps/inout/`) drafts geostat's modules field for field; merged over geostat's
manifest it changes no declared leaf and adds only `commands.lint` and `layout.profile`; a
gesotat-shaped multi-service Gradle build is one `java-boot` module; ambiguity is refused; a project
driver's evidence claims; `--plan` writes nothing and `--approve` records who.
`tests/acceptance/test_draft_cli.py` drafts through the CLI. Run read-only against geostat's own
tree, the draft adds the same two fields and changes nothing.

**Not derived, by design:** a module's `launchProfile`, `configuration`, `publishExpect`,
`toolchain.version`, `node.scripts` and the secrets root are the host's decisions, so they are kept,
never drafted. **Owed:** the scaffold `init` writes for a new project (`apps/`, `tools/`,
`kits/stack-kit`) is not yet the `monorepo` profile it now declares. Moving the scaffold onto
`platform/apps/<app>/{backend,frontend}` and `platform/kits/` changes every new host's paths, so it
is its own change.

## Amendment 11 — CD generated from the declarations: build once, promote the same bytes (2026-10-16, owner-delegated)

The owner: stack-kit carries CI/CD mechanisms, not only CI. `ci-gen` now generates the delivery too,
from the manifest and the deploy targets, with no hand-written workflow.

1. **Build once.** A driver declares its `package` step (`{command, args, artifacts}`, `{out}` its
   staging directory); `stack-kit package <module>` runs it (recorded) and archives what it left as one
   file named by the commit, `.stack-kit/artifacts/<module>-<sha>.tgz`, with its sha256.
   `stack-kit unpack` restores those bytes where the release reads them, and refuses an archive whose
   sha256 differs or a member that would land outside the module. In CI the package step runs on the
   default branch in the module's own job, beside an SBOM (`anchore/sbom-action`, SPDX) and a
   build-provenance attestation (`actions/attest-build-provenance`), and is uploaded once.
2. **Promote the same bytes.** A release rung that `promotes` (operands that deploy a packaged
   artifact without building: `java-boot` `--no-build`) is the only kind CD deploys. `deploy-dev` runs
   on the default branch after every promoted module's job; `deploy-prod` needs it and runs in a
   GitHub Environment named after the prod target, so its protection rules (the owner's approval) gate
   it. Each job downloads and unpacks the archive, delivers (`mod <id> deliver release --env <e>
   --target <t> <promotes>`), and verifies (`targets --health`: the target's declared health URLs;
   `targets --verify`: the tree). Prod never builds: no lifecycle step runs in a deploy job.
3. **Parity.** Every step is the command a developer runs; the workflow only sequences them.
4. **Secrets only from the CI store:** `STACK_KIT_SSH_KEY_<TARGET>` into ssh-agent,
   `STACK_KIT_ENV_<FOLDER>_<ENV>` written as the module's env file (`umask 077`). Host keys are the
   target's tracked `known_hosts` (the resolver's `ssh-args`). One concurrency group per target and
   environment, never cancelled; the workflow-wide group cancels only pull-request runs, so a newer push
   never stops a deploy halfway.
5. **DORA.** Every package and deploy job uploads `.stack-kit/runs/runs.jsonl` as a
   `stack-kit-runs-<job>` artifact (`if: always()`): the deployment events with commit, start, end and
   exit, from which frequency, lead time and change failure rate are computed. GitHub Deployments are
   also recorded by the Environment jobs themselves.
6. **CI only, and why.** Without reachable `defaults.dev` and `defaults.prod` targets, or without a
   module whose package and release can promote, no deploy job is generated, and the workflow's header
   lists each reason (`no deploy targets are declared`, `target <t> (prod) is pending: ...`,
   `<module> (<driver>): packaging is pending -- ...`). `ci-gen --check` stays the drift gate.

**Declared per driver today:** `java-boot` packages its boot jars and promotes with `--no-build`;
`dotnet-aspnet` packages its `dotnet publish` output (its delivery to a server -- IIS -- is pending);
`node-spa` packages its `dist/` (its release is pending); `node-vite` packaging is pending (its build
compiles the environment's API URL in -- one artifact needs runtime config); `node-api` packaging is
pending (its image is built on the server). **Pending:** rollback on a failed verify by re-pointing
`current` waits for the release delivery of amendment 9; a release's own health gate (java-boot)
already rolls back to the previous artifact.

Pinned and verified with `git ls-remote` on 2026-10-16: `anchore/sbom-action` v0.24.3 (an annotated
tag; the pin is its peeled commit `66cbf4bc…`), `actions/attest-build-provenance` v4.2.2,
`actions/upload-artifact` v7.0.2, `actions/download-artifact` v8.0.2 (lightweight tags).

*Rejected:* building per environment (the bytes in prod would not be the bytes tested in dev);
deploying from a job that also builds (a rebuild hides in a convenience); `workflow_run` chaining
(two files to keep in step; one generated file is one drift gate).

Proof: `tests/unit/test_cd.py` (the generated jobs, needs, environments, concurrency, secrets,
commands and the absence of any build step in a deploy job; CI only with each reason; the archive's
round trip, its sha256 and an escaping member refused; `--health` against a local HTTP server),
`tests/acceptance/test_lifecycle.py` (`stack-kit package` through the real CLI).
**Nothing has run on GitHub:** the workflow is proven as generated text and its commands as local
runs, until the owner pushes it.

## Amendment 12 — extension is a declaration; the kit stays untouched (2026-10-16, owner-delegated)

An independent extensibility audit measured that a new driver (`python-fastapi`) needed four kit files
changed, and that script languages were closed at two. Each finding, fixed by a declaration a project
can extend, and proven by a test that adds the case with the kit untouched:

1. **Script runtimes are declared** (`config/runtimes.json`; a host adds or overrides one in
   `runtimes`): `match` globs on the script's name and an `argv` template (`{script}`, `{operands}`,
   `{bash}`, `{python}`, `{pwsh}`), or `inSession` for PowerShell, the one runtime whose `-Name`
   operands bind to declared parameters. A command is `"path"` or `{script, runtime}`. The CLI used to
   introspect every non-`.sh` script as PowerShell, so a `.py` with a `-Flag` operand crashed. The
   registry's `runtime` field was dead (java-boot said bash and its build is `.ps1`): removed, and read
   with a notice where a project registry still carries it. `drivers/registry.schema.json` -- never
   loaded before -- now holds the composed registry in `validate`, every field typed and a misspelt
   one refused; roles are held to the roles catalog in code.
2. **No driver is named outside its directory.** Compose templates (`compose.templates`), Dockerfiles
   (`compose.dockerfiles`), the ops-modules registry (`compose.opsModules`), the nginx-served UI
   (`nginx.serves`), the layout simulators (by the simulator a driver declares) and the CI fallback
   module (by deploy kind) are driver declarations; `compose-catalog.json` lost `templateKey`, and a
   host's catalog may add module templates (`moduleTemplates`). `config_gen` asks the `configGen`
   capability under its own name. `test_declared_agnosticism.py` is deny-by-default over every tracked
   `*.py`, `*.ps1`, `*.sh` outside `drivers/` and `tests/`, in hyphen and underscore spellings, comments
   included -- an allowlist of cured files is how an uncured one stays unseen.
3. **CI pins and launch configurations are open.** `ci.actions` names the host's own pin file, still
   full SHAs only (a tag is refused); a driver's `vscode.launch` may be data with `{module}`,
   `{path}`, `{label}`, `{script}` filled per module; a driver's `ci.runsOn` and a target's `runner`
   choose the CI runner.
4. **One declared catalog each** (`config/catalogs/`, extended in the manifest's `catalogs`, an entry
   inserted `after` another): **roles** (`deployOrder`, `bootOrder`, `primaryService`,
   `serviceOverride`, `primaryField`, `launchCompound` -- replacing copies in modules, stack_deploy,
   dev up, vscode-gen, the compose naming switch and both schemas; the compose naming no longer
   privileges a module named `frontend`), **environments** in promotion order (`workspace`,
   `runDefault`, `deployDefault` -- replacing the dev/prod lists and ValidateSets in envfile, targets,
   the resolver, env.ps1, the host runner, Deploy-Path.ps1, the CLI and the schemas), **lifecycle**
   steps (`optional`; each is a CLI verb and a CI step) and **target runtimes**. Adding `staging` or
   `typecheck` touches no code: `tests/unit/test_extension.py` and
   `tests/acceptance/test_extension_cli.py` add both by declaration and run them -- a host run in
   staging reads `.env.staging`, CD promotes dev -> staging -> prod, `stack-kit typecheck` runs a
   project driver's step under a project-declared runtime.
5. **Small.** A malformed registry is refused by name (it read as `{}`, silently removing every
   driver). `stack-remote.sh` finds the project through the resolver, not two levels above the kit.

**Not catalogued, and why:** the `validate.stages` kinds (`setup` ... `anchor`, `teardown`) are the
proof grammar the pipeline interpreter enforces (an anchor compares, teardown always runs), not a
step a driver runs. The kit's own drivers' flag grammars (`java-boot` deploy's `--dev|--prod`) are the
driver's code: a host adding `staging` declares it in the catalog, and a driver that must learn it
learns it in its own directory.

*Rejected:* a plugin API in code for each extension point (a second grammar beside the registry's);
keeping the closed enums in the schemas and adding an overlay schema (two homes for one list).

**Owed, recorded, not done now:** split `cli/stack-kit.ps1` into discovered verbs (as the agent kit
discovers its verbs from files), and `lib/resolution.py` and `lib/targets.py` into smaller modules;
remove the import cycles behind the function-local imports (`modules` <-> `project_context`,
`modules` -> `stack_deploy`, `catalogs` -> `project_context`); fold the per-ecosystem deploy pipelines
in `toolkit/deploy/` (`node-upload.sh` "mirror of upload.sh", `node-docker-up.sh`, `pnpm-build.sh`
beside `gradle-build.sh`) into one generic container pipeline whose steps a driver declares.

## Amendment 13 — one generic pipeline, one operator CLI, one home per value (2026-10-16, owner-delegated)

**Context.** After amendment 12 every extension point was a declaration, but delivery was not: each
driver shipped its own deploy, dev and manage scripts (`toolkit/deploy/*`, `node-upload.sh` beside
`upload.sh`, `gradle-build.sh` beside `pnpm-build.sh`, the PowerShell and bash manage helpers), a
value could live in four places (the manifest, deploy.env, a folder's `.env.deploy`, a process
variable), the server layout had no tier, a release was a folder of versioned jars, and the CLI was
one 659-line PowerShell file. The platform host the hosts share is one root holding many projects'
tier-first folders; its compose is the standalone binary; Windows developers have no rsync.

**Decision.**

1. **One home per value.** Every name is `lib/naming.py`'s (the manifest's `project`, else the
   folder); every remote path is `lib/targets/layout.py`'s, strictly under `{root}/{project}`; the
   engine and compose invocations are the target runtime's declaration (a target's `compose` over it);
   the local ones the runtime flagged `local`. deploy.env, `.env.deploy`, DEPLOY_*, COMPOSE_*_SERVICE,
   COMPOSE_PROJECT_NAME, DOCKER_NETWORK, INFRA_SLUG, `stack.networkName`, `roles.serviceOverride` and
   the kit's former names are no longer read: each is a `validate` error naming `migrate`, the one
   reader left, which carries it (the manifest's `project`, a target, its `ports`, its `legacyLayout`)
   and removes it. Held deny-by-default (`tests/unit/test_one_home.py`): no generic script names a tool,
   each declaration file has one reader, a former key is spelled only by `lib/legacy.py` and
   `lib/migrate_legacy.py`, no remote path is composed outside the layout, no import cycle.
2. **Tiers.** `config/catalogs/tiers.json` (backend, frontend; host-overlayable); each role names its
   tier; a unit is `{root}/{project}/{environment}/{tier}/{service}` with `releases/<commit>`,
   `current`, `runtime/`, `logs/`, `workspace/`; an environment holds `stack/` (`compose.yml`,
   `env/<service>.env`, `state.json`), `infra/`, `backups/`. `targets --plan` renders it.
3. **One generic pipeline** (`lib/delivery/`): package (the driver's `package` step, then one archive
   per commit with `release.json`: commit, `git describe`, dirty, services, each service's tree with
   its recipe -- the module's Dockerfile or the driver's template rendered for it) -> ship
   (`releases/<id>.partial`, then moved) -> env file (600), runtime config and credentials (read-only
   mounts) -> `current` -> the environment's one compose file (derived JSON, namespaced) -> build an
   image only when the engine lacks it -> up -> health (the engine's status; no healthcheck = running)
   -> prune to `keep`, never `current`. An environment declares `requireClean`, `rollbackOnFailure`,
   `confirm`. Drivers declare `container` and `dev`; every packaging driver releases `via: release`.
4. **Remote dev** on the same layout: `dev up/down/sync/watch/logs/status/shell/tunnel`; a sync is rsync
   when both ends have it, else an index (size, mtime, hash) + one tar stream over ssh, deletions held
   inside the workspace, one exclude list (never env files, keys, credentials; the driver's and the
   module's excludes; its .gitignore); `watch` polls, debounces, reacts as declared (hot-reload,
   restart, rebuild), reconnects and resyncs.
5. **The operator interface is one CLI** (`lib/cli/`: discovered verbs, each with `--help`, options,
   exit codes, examples). A remote verb prints its plan -- every path and command -- before it acts;
   `--plan` stops there; a confirming environment asks on a terminal and refuses without one unless
   `--yes`. `cli/stack-kit.ps1` and `.sh` only find Python. CD calls the same CLI (`deploy
   --artifact --yes`) with a `workflow_dispatch` environment choice and GitHub Environments.
   `docs/OPERATIONS.md` is rendered from the registry and drift-tested.
6. **Ownership on a shared root.** Nothing acts on `{root}`. `targets --init` claims an absent or
   empty project directory with `.stack-kit-project`; a non-empty one without it is refused, as is one
   another project marked; `rm`/`nuke` act only inside a claimed environment. `layout migrate` moves
   only what a target's `legacyLayout` declares as this project's, never a direct child of the root,
   plan by default, `--approve` to apply. `targets --verify` reads the declared state against the host
   -- places, marker, compose file, env and runtime-config digests, each service's running release,
   runtime, ports, disk -- read-only.
7. **The splits owed by amendment 12.** `lib/targets/` (declaration, layout, remote), `lib/resolution/`
   (context, resolver, infra), `lib/cli/` (main, registry, verbs); a leaf `lib/project_root.py`; no
   import cycle. Removed: every driver deploy/dev/manage/compose/check script, `toolkit/deploy`,
   `toolkit/bash`, `toolkit/powershell`, `toolkit/layout` (the 855-line simulator superseded by
   `targets --plan`), `toolkit/stack`, `gen_server_compose.py`, `ensure-prereqs.sh`, `deploy_paths`,
   `stack_deploy`, the per-driver migrate scripts, `package unpack`, the `promotes` concept.

**Proof.** A recording transport with a fake engine (`lib/delivery/fake_server.py`) and a directory
standing in for a server (`LocalTransport`, the sync fallback end to end): releases, idempotence (a
second release changes nothing), prune, rollback on failed health, provenance refusals, the marker on
a shared root with foreign tier-first folders, the port preflight with many foreign ports, the
declared compose invocation, migrate-layout, verify, remote dev and watch with a lost connection --
through a project-declared driver, tier, environment and target runtime the kit does not ship.

**Unproven, and only this:** the layout's `unproven` -- the delivery against a real docker host.
**Pending:** Windows/IIS delivery (the `iis` runtime). **Owed:** `lib/vscode_gen.py` and two
compose-gen helpers still name tools (a shrinking list in `test_one_home.py`).

*Rejected:* a YAML library for the stack (compose reads JSON); one compose file per unit (the
environment's network, ports and dependencies are one document); image registries (the platform has
none; a release builds its image once on the host from the shipped bytes, skipped when present);
`--reconcile` (drift is undone by the verb that owns it); keeping deploy.env as a read fallback (two
homes drift; the error plus `migrate` costs one command once); a PowerShell CLI with Python helpers
(two languages for one dispatch).

## Amendment 14 — what the earlier efforts proved, carried as mechanisms (2026-10-16, owner-delegated)

**Context.** The two earlier platforms solved real failures the kit did not yet prevent: images run
as root with no health probe, SPAs that bake addresses in and need CORS, backups nobody restored,
migrations edited after they ran, CI that skips its database tests, secrets in history, floating
images, unvalidated env values, TLS on a network without a public CA, logs that fill a shared disk.
The owner's gate: build only what prevents a real failure, saves measured time or raises measured
quality for our hosts; record every cut.

**Decision (each a declaration, each tested).** Recipes run unprivileged with a HEALTHCHECK that asks
the declared `healthPath`, else only that the port answers; a static app runs on an unprivileged
nginx (same-origin proxy for declared paths, nosniff, Referrer-Policy, gzip, immutable hashed assets,
no-cache HTML, `/healthz`) and a built bundle with a plain-http URL or an IP is refused; a release
refuses `latest` or untagged images (digests where `requireDigests`), images its scan policy refuses
(`security.imageScan`: a digest-pinned scanner, failOn, observeOnly, maxDbAgeHours, OpenVEX
waivers), and env values its policy refuses (`config.keys` `policy`: required, minLength, format,
forbid, requires; `stack-kit config check`); secrets marked `generate` are made on the server once
and given as `<NAME>_FILE`; one injection contract `STACK_KIT_ENV_FILE_<FOLDER>_<ENV>`; logs rotate;
a layout that lets two environments share a place is refused. `backup` / `backup verify` (a
throwaway restore checked against the host's anchors, always dropped); `stack.migrate` runs before
the apps, `migrations lock` keeps a checksum ledger validate holds; `ci.database` gives CI a healthy,
migrated database; `scan secrets [--history]`; the `audit`, `e2e`, `visual` step kinds; infra
templates (SQL Server, Postgres, Redis auth, MinIO, OTel, Prometheus, Grafana, Tempo, Keycloak,
Flyway, the edge); `tls ca|leaf|truststore`; OIDC readiness in `targets --health`; `ops
restart-check`; `ops prune [--schedule]` (cache and dangling only). `config/conformance.json` maps
each standard clause to its mechanism, its evidence and its status, machine-checked.

*Cut, recorded as non-goals (cost exceeds benefit):* a secure compose overlay (the env-value policy
covers it), evidence sidecars (attestation covers it), changesets, named log sources and a reload
verb, `deploy watch` (dev watch covers it), `--reconcile`, load and watchdog probes, the MATURITY and
DEV-MODES pages. *Partial, with why:* SQL Server's restore check is VERIFYONLY; no fresh-chain replay;
no live-parity CI job; java-boot declares no audit; the scanner's digest is the host's to pin.

## Amendment 15 — every host extension through a declared point (2026-10-16, owner-delegated)

**Decision.** `config/extension-points.json` (the shape agent-kit shares: id, purpose, host_path,
template, schema, cardinality, required_by, merges_into) declares every place a host extends the
kit. `extend --list`, `extend <point> [<name>] [--plan]` (on demand, idempotent, never overwriting),
`<<pending: ...>>` markers validate shows (an error where `extend.profile` requires the point),
`extend --upgrade` (a 3-way merge of a changed template, a conflict reported and the host's file
kept), and an undeclared file where a point lives is reported. Folded in, not kept beside it: init is
`extend --init` (the scaffold is the template store; infra services on demand), `init --plan` is
`extend module`, the catalogs overlays are points. *Rejected:* a tree of empty extension files
(they rot and look complete); copier/cookiecutter as a dependency (the kit needs one merge, git has it).

**Owed after amendment 15 (one line each):**
- The delivery against a real docker host (the layout's `unproven`); Windows/IIS delivery (`iis` pending).
- ~~`lib/vscode_gen.py` and two compose-gen helpers still name tools~~ -- closed by amendment 16.1.
- ~~SQL Server's restore check is VERIFYONLY; no fresh-chain migration replay~~ -- built by amendment 16.3; unproven against a real server.
- No separate live-parity CI job. (~~java-boot declares no dependency audit~~ -- closed by amendment 16.2.)
- The image scanner's digest is the host's to pin; the kit ships no default scanner.
- The kit's schemas are draft-07, not JSON Schema 2020-12; commit messages are not machine-checked.
- ~~Extension points: mirrored by field names only~~ -- the shared schema is vendored and the registry validated against it (amendment 16.4).

## Amendment 16 — the owed list after amendment 15, closed where it can be (2026-10-16, owner-delegated)

1. **No generic file names a tool.** A module's VS Code launch is its driver's declaration
   (`vscode.launch` as data, rendered by the one template grammar), with the `values` it reads from
   the module's files -- `field` (`exists`: a declared file that is missing is an absence, never a
   fallthrough), `driver`, `value`, `glob` (`single`, or the shortest; `as: dotted` under a root),
   `file` + `capture` -- its `label`, and the keys that are `optional`. The three builders in
   `lib/vscode_gen.py` (and the Full-stack compound that picked launches by debugger type) are gone:
   the compound takes the first launch of each compounded role in the roles catalog's boot order;
   the kit's own terminal launch type is a convention default (`vscode.terminalLaunchType`, the
   scaffold manifest). The local compose-gen's ops.modules rows -- kind, header columns, the
   embedded worker row, the shared build module's marker and row -- are `compose.opsModules` of the
   driver that owns them. `test_one_home.py`'s owed list is empty. *Rejected:* a builder per launch
   kind registered by drivers in code (a second grammar beside the registry); keeping the string kinds
   as aliases (two homes for one launch -- a former kind is now a schema error naming the data form).
2. **java-boot declares a dependency audit**: `audit` (`py/audit.py`) runs OSV-Scanner (OpenSSF's,
   over the OSV database that aggregates GitHub, NVD-derived and ecosystem advisories) over the
   module's Gradle dependency lockfiles -- the binary when it is on PATH, else its image
   (`ghcr.io/google/osv-scanner`, a version tag the driver declares; a module's `audit.image` pins
   a digest) through the local engine, so a CI runner needs no install. A finding fails the step; a
   waiver is OSV-Scanner's own `osv-scanner.toml` with a reason; a module that locks nothing is
   refused, since an unlocked graph resolves differently tomorrow. *Rejected:* the OWASP
   Dependency-Check Gradle plugin (it must be added to the host's build -- the kit would edit
   application code -- and it needs an NVD API key and a multi-minute database download per run);
   a Gradle `dependencies` report parsed by the kit (a second resolver beside Gradle's).
   *Unproven here:* no scanner runs in the suite (the command line is recorded); the image tag is
   not digest-pinned by the kit.
3. **SQL Server restores into a throwaway database; the chain replays from empty.** `backup verify`
   restores every store into a uniquely named database (`stack_kit_restore_check_<UTC>_<random>`):
   SQL Server by `RESTORE FILELISTONLY` then `RESTORE DATABASE ... WITH MOVE` each logical file to a
   name of its own (never over the source), `CHECKSUM, RECOVERY`, replacing `VERIFYONLY`; the anchors
   are queried in the restored copy (they asked the live database before); the store's `drop` runs
   in a `finally` (pass, fail or error). sqlcmd reads its password from `SQLCMDPASSWORD`, never an
   argument. The same throwaway lifecycle gives `backup replay`: a store that declares `create`
   makes an empty database, the migration service that declares `replay` (`env`, `urls.<store>`,
   flyway's JDBC URL) is run against it with the whole chain, the host's `stack.migrate.replay`
   anchors are queried there, and it is dropped. Both verbs print their plan first. *Rejected:* a
   second SQL Server container per check (the data volume and memory of a second instance on a
   shared host, for no isolation a database name does not give); `DBCC CHECKDB` in the check (hours
   on a large database; the host may add it as an anchor). *Unproven:* against a real SQL Server or
   Postgres -- the suite proves the commands and their order with the recorded transport only.
4. **One extension-point shape, vendored from its origin.** `config/extension-points.schema.json` is
   agent-kit's `kit/schemas/extension-points.schema.json`, byte for byte (commit `3b1593f`, sha256
   `959c6aa0...196e`), recorded in `config/vendored.json`; `tests/unit/test_vendored.py` holds the bytes
   to the record, compares the origin where its checkout sits beside the kit, and validates
   `config/extension-points.json` against it. The kit-local schema it replaces is gone, and the
   registry moved into the shared shape: `schema_version`; `schema` and `template` always present
   (`null` for none); `required_by` one profile or `null` -- `init` is the base profile (init lays the
   point down, every declared profile requires it), so `targets` is `init` and `target` `release`;
   no `$comment`; `companions` became a rule of ids (`<id>-entry` is made with `<id>`), since the
   shared shape has no field for it. *Rejected:* a stack-kit overlay schema adding `companions` and
   array `required_by` (a second shape for one registry); deriving the registry at run time from
   other declarations as agent-kit does (stack-kit's points are declared nowhere else -- the file is
   their one home).
5. **Non-interactive by construction.** `ssh_args` puts `-o BatchMode=yes` first for every target
   (openssh keeps an option's first value, and a command-line option wins over a `-F` config); a
   target whose `ssh.options` says otherwise is refused by name. The target template no longer
   carries it -- one home. *Rejected:* a validate warning only (a deploy could still hang on a
   prompt in CI).
6. **Isolation by data source** (found on a real host: its dev and prod runtime configs named the same
   server and databases, and the isolation check compared only places). A catalogued key may be a
   `dataSource`; each environment's value of it is read where the application reads it -- the
   module's env files for that environment, the shared `.env` included, and its declared runtime
   config files -- and reduced to its identity (server with port or instance, database), parsed from
   ADO.NET, libpq, URL and JDBC forms (`lib/data_sources.py`). Two environments with one identity are
   refused by a deploy of either (exit 4) and reported by `validate` (a warning: the deploy is the
   gate), unless `config.sharedDataSources` or a target's `sharedDataSources` declares it with a
   reason. A finding names the key, the environments and the files, and an 8-hex fingerprint --
   never a value, a host or a database name. A host under `.invalid` is the kit's "no store here"
   sentinel, never shared. *Rejected:* comparing whole values (two spellings of one database would
   pass, and a whole value is a credential); resolving hosts to addresses (a network read in
   validate, and DNS differs by vantage point).
7. **What a deploy runs is visible in the host** (owner request: the effective Dockerfile lived in the
   driver, the per-environment compose only on the server). One new verb, `render` (`--plan`,
   `--check`), writes generated projections -- each deployable module's effective recipe (its own
   `container.dockerfile`, or its driver's template, a host driver's included, rendered for it) to
   `projections.containers` (default `ops/containers/{module}/Dockerfile`), and each environment's
   stack compose as deploy writes it on its target to `projections.stack` (default
   `ops/compose/stack/{environment}/compose.yml`) -- each under one header line naming its sources.
   Two values exist only once a commit is packaged and are symbolic: the release id (`{release}`)
   and the artifact's file name (the driver's `container.artifact` glob); a credential is the one
   the module declares. `validate` reports a projection its sources no longer render (an error) or
   one not rendered (a notice); a release refuses a stale one (exit 5), comparing the archive's
   recipe and the very service documents it is about to write. *Rejected:* extending `compose-gen`
   (it generates the LOCAL development stack; one verb per output keeps each honest); committing
   projections with the concrete release id (stale on every commit); rendering the compose as YAML
   (compose reads the JSON deploy writes; a second serialiser would make two byte forms).
8. **Env files are the kit's job, from the one catalogue** (`lib/envgen.py`). Each secrets folder's
   committed `.env.example` is a projection of `config.keys` -- every key of the folder (its
   `policy.modules`, else every folder), its sensitivity, where it is required, a data source, a
   generated key, a non-secret key's default and per-environment values, a secret's value always
   empty -- written by `render` and held by validate's projection drift. `extend env <folder> --env
   <id>` makes the ignored `.env.<id>` once (never overwritten, mode 600, refused when git would track
   it): a PUBLIC or INTERNAL key's `environments.<id>` value, else its `default`; a SECRET as a
   `<<pending: ...>>` marker, which `config` reports and a deploy refuses (exit 4); a generated key
   (`policy.generate.bytes`, or its shorthand `generate: "random:<bytes>"` -- one reader,
   `config_policy.generate_bytes`) a fresh value, never printed, and never shipped in a deploy's env
   file (the server makes its own once, umask 077, given as `<NAME>_FILE`); a data source the
   environment declares `none` the sentinel `Server=none.invalid;Database=none`, which the isolation
   check never counts as shared. A SECRET with a per-environment value other than `none` is a
   committed secret and refused. *Rejected:* `env` as a registry point (an ignored, machine-local
   file is no host extension of the kit: nothing to commit or upgrade 3-way); keeping hand-written
   examples beside the catalogue (two homes drift).
9. **A module keeps files out of its images** (a real host must keep secret-bearing settings files out
   of a deployed image until their rotation). `modules.<id>.package.exclude` -- gitignore-style
   patterns, the remote-dev sync's own matcher -- is applied by `pack`, the one package step every
   driver goes through, from the artifacts' root (the module, or the staged `{out}`), so an excluded
   file is in no archive and no image of the module whatever its driver. The archive's `release.json`
   -- the provenance CI attests -- records the patterns and the files they kept out. *Not changed:*
   the SBOM is still of the module's source tree (it lists dependencies, not files); a remote-dev
   workspace keeps files out by the module's `dev.excludes`. *Rejected:* a per-driver exclude (every
   driver would carry the same rule; one step holds it).
10. **The scan's patterns may be the host's.** `security.secretPatterns` names one or more documents
   of agent-kit's edit-gate contract (`gates[]`: `id`, `paths`, `forbids`, `proves`, `admits`), read
   by path -- the kit imports nothing of agent-kit. Each gate is a scan rule (its `forbids` applied
   per line, on the files its `paths` matches), used only once its own calibration holds (it refuses
   its `proves` and admits its `admits`), else the scan refuses to run (exit 2) and validate names
   it. The kit's four built-in pattern rules apply only when no document is declared; the structural
   rules (a committed env file, a tooling binary, a known leak) always hold; a declared document is
   not itself scanned (it carries its calibration). validate warns where `security.allow` names a
   rule the declared set lacks -- the one way a host can declare both. *Rejected:* merging the
   built-in set with the declared one (two policies for one boundary, and a host could not retire a
   noisy built-in); importing agent-kit's judge (a dependency between kits that share only shapes).
   The contract's own field names are used (`gates[].forbids`), not the `rules[].pattern` the request
   named, since that is the document the host already holds.
11. **Templates are placed for the host.** The init points that named `apps/backend`, `apps/frontend`
   and `ops/config/backend|frontend`, and the compose catalogs' paths, carry placement tokens
   (`lib/extend.py`): `<tier:T>` the path of the host's first module whose role lives in tier T,
   `<secrets:T>` that module's secrets folder, `<up:T>` the way back from it to the root -- else the
   layout profile's `tiers.T` (the monorepo profile: `platform/apps/{project}/T`), else `apps/T`, so
   a default host is laid down byte for byte as before. They are rendered in a point's host path and
   in a template's text (with its `{field|default}` manifest fields), at init from the manifest as it
   stands (a host's own, or the one init just wrote), on `extend --upgrade` too, and in init's minimal
   compose catalog. *Not changed:* the scaffold manifest's sample modules keep `apps/<tier>` -- it is
   the convention-defaults source, and a host with modules of its own never takes it.
   *Rejected:* a template per layout (the same files twice).
12. **Build output is never tracked** (`lib/tracked_outputs.py`): each driver declares what its toolchain writes as `outputs` (gitignore-style, relative to the module; the former `generated` directories, now also what draft and the remote-dev sync skip), a module adds its own in `modules.<id>.outputs` (never a removal), and validate refuses every file git tracks under a module that an output matches -- one error per output, its file count, `git rm -r --cached` and the .gitignore line. *Rejected:* a kit-wide list of build directories (a new driver would be unknown to it; the driver is the one that knows).

**Owed after amendment 16 (one line each, the truth at 2.2.0):**
- Every delivery, restore and replay is proven against the recorded transport only: unproven against a real docker host, SQL Server or Postgres.
- Windows/IIS delivery (`iis` pending): a host that publishes to IIS by hand keeps its own publish.
- No separate live-parity CI job.
- The image scanner's digest, and the OSV-Scanner image's, are the host's to pin; no scanner runs in the suite.
- A static service's server config is not projected by `render`; the release id and artifact name are symbolic in projections.
- The kit's schemas are draft-07, not JSON Schema 2020-12; commit messages are not machine-checked.
