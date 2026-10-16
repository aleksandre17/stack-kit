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
