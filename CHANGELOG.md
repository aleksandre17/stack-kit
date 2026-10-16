# Changelog — stack-kit

## 1.2.0-dev — unreleased

### Extension is a declaration (ADR-001 amendment 12)

- Script runtimes declared (`config/runtimes.json`, manifest `runtimes`); a command may be
  `{script, runtime}`. **Removed:** the registry's `runtime` field (read with a notice).
- `validate` holds the composed registry to `drivers/registry.schema.json`; a malformed registry is
  refused by name.
- Catalogs (`config/catalogs/`, manifest `catalogs`): roles, environments, lifecycle steps, target
  runtimes; every lifecycle step is a CLI verb; adding `staging` or `typecheck` touches no code.
- Driver capabilities replace every driver id outside `drivers/` (compose templates, Dockerfiles,
  ops modules, nginx, layout simulators); `compose-catalog.json` lost `templateKey`.
- `ci.actions` (project pins, SHA-only); `vscode.launch` as data; `ci.runsOn` / target `runner`.
- The compose naming no longer privileges a module named `frontend`.

### CD generated: build once, promote the same bytes (ADR-001 amendment 11)

- `stack-kit package <module>` / `unpack <module> <archive>`: the driver's declared `package` step, one
  archive per commit (+ sha256); drivers declare `package` (or `pending`) and a release's `promotes`.
- `ci-gen` adds, on the default branch, package + SBOM + build-provenance attestation per module, and
  `deploy-dev` -> `deploy-prod` (GitHub Environment per target, concurrency per target/env) that unpack
  the same archive, deliver, and verify (`targets --health`, `targets --verify`); CI only, with the
  reasons, without reachable targets or a promotable module. Run records uploaded per job.
- `targets --health`: a target's declared `health` URLs per environment.

### The manifest is drafted from the tree (ADR-001 amendment 10)

- Drivers declare `detect` (the evidence a directory is their module, and what they read from it);
  `init --plan` drafts modules, aliases, `commands`, `layout.profile` as additions against the current
  manifest; `init --approve <who>` writes them (`draft.approvedBy`). Declared fields always win; a
  directory two drivers claim is refused.
- `layout.profile`: canonical trees declared in `config/layout-profiles/` (`monorepo`), derived as floor rows.

### Where a deploy goes is declared (ADR-001 amendment 9)

- **Deploy targets:** manifest `deploy.targets` names `ops/deploy/targets.json` (tracked, no secrets;
  schema `config/deploy-targets.schema.json`), merged under a gitignored `targets.local.json`. Per
  target `host`, `user`, `port`, `root`, `runtime`, `ssh` (identity reference, pinned `knownHosts`,
  `hostKeys`), `layout`, `ports`, `keep`, `pending`; `defaults` per environment. `--target <name>` on
  any verb.
- The resolver answers the server, ssh options (`ssh-args`; `StrictHostKeyChecking=yes`) and every
  remote path (`remote-path`) from the selected target; the shells only ask it.
- **Default remote layout** (`config/deploy-layout.default.json`): `{root}/{project}/{environment}/`
  with `modules/{service}/`, `stack/`, `infra/`; any template overridable per target.
- **Isolation:** every path refused outside `{root}/{project}/`; an ownership marker
  (`.stack-kit-project`) written or checked before any write; compose project `{project}-{environment}`;
  declared ports unique per host and checked against other compose projects at deploy; removes and
  prunes confined; node-vite staging moved inside the module's directory.
- `stack-kit targets [--plan|--verify]`: each target; the whole tree; read-only drift over ssh (exit
  1 drift, 2 not verifiable).
- `modules.<id>.runtimeConfig[]` declared and validated (no secret).
- Deploy provenance: `IMAGE_REVISION` into compose; a prod deploy from a dirty checkout is refused.
- **Deprecated:** `deploy.env` `DEPLOY_SERVER`, `DEPLOY_SERVER_BASE`, `DEPLOY_PATH`, `DEPLOY_LAYOUT`,
  `DEPLOY_PATH_MODE`, `DEPLOY_SSH_*` (read until 2.0.0 on a host without targets; `validate` names
  them; `migrate --apply` declares them as a target). `/home/deploy` is no longer a fallback.
- Pending: the release/`current` delivery, `stack/` compose, runtime-config upload, namespaced
  container/network/volume names (need a docker host to prove).

### A new project works with no setup of its own (ADR-001 amendment 8)

- **Breaking: a run on this machine reads one environment.** `run` / `hybrid boot` read the
  module's shared `.env`, then `.env.dev`; `.env.prod` only with `--env prod`. A development run no
  longer fills from `.env.prod`. `validate` / `migrate` name, per secrets folder, the keys it lost.
- Lifecycle steps per driver: `build`, `test`, `lint` (`dotnet-aspnet`: dotnet build/test/format;
  `java-boot`: Gradle build/test; Node family: package.json scripts through
  `toolkit/node/Invoke-PackageScript.ps1`). `stack-kit build|test|lint [module ...]`: every module,
  fail-fast, the step's exit code.
- New driver `node-spa`: any SPA by its own package.json scripts (Angular CLI, Vite, React, Vue).
- Manifest `commands` {`test` (required), `build`, `lint`, `run`}: literal command lines for every
  tool; the scaffold writes them through the launcher; `validate` checks the scripts they name.
  New fields: `dotnet.solution`, `dotnet.test`, `node.scripts`, `node.packageManager`,
  `toolchain.version`, `ci.workflow`.
- `stack-kit ci-gen [--force|--check]`: `.github/workflows/ci.yml` from the modules, actions pinned
  by verified SHA (`lib/ci-actions.json`); `init` writes it.
- `init` works again (it failed at its first Python call) and its result validates; module env
  examples moved to `ops/config/<module>/.env.example`; the scaffold ships an nginx template.
- Run record: one JSON line per `deliver` rung and lifecycle step in `.stack-kit/runs/runs.jsonl`
  (self-ignoring).
- Layout migrations find their module by `deployKind`, not by driver name; deploy markers name the
  module that wrote them.
- Hygiene: no BOM outside PowerShell; every non-ASCII `.ps1` carries one (Windows PowerShell 5.1);
  README quick start; license pending; `vendorDirs` + `platform/kits/stack-kit`.

### The owed list, closed (ADR-001 amendment 7)

- **Breaking for a host on the former keys, carried by `migrate --apply`:** `ci.<name>` script paths
  the schema spelled for one consumer (`ragSmoke`, `ragEval*`, `chat*Smoke`, `corpusQualityAudit`,
  `verifyServicesProd`, …) → `ci.scripts.<name>`; `modules.<id>.catalog` / `.derivation` →
  `modules.<id>.extensions.*`. The module object is closed: an undeclared field is refused.
  `validate` names the door. Each `ci.scripts` path must exist and is a layout-floor row.
- `run` is the kit's host runner for every driver that declares `hybrid.script`
  (`lib/modules.driver_commands`); the four `drivers/*/ps1/run.ps1` delegates are deleted.
- `stack-deploy` names no driver: the environment is the release rung's `--{environment}` and the
  options a rung passes on are its `forwards` (`java-boot`, `node-api`: `--no-build`,
  `--skip-checks`). `node-api` now deploys the environment asked for. The runner calls the kit's
  CLI, not a host's `tools/stack-kit.ps1`.
- `lib/driver_api.py` and `lib/modules_cli.py` folded into `lib/resolve_cli.py` (`driver-types`,
  `driver-command`, `stack-steps`, `stack-health`, `stack-endpoints`, `compose-names`,
  `compose-service`).
- `lib/module-manifest.ps1` deleted; a driver reads its own fields with `Get-ModuleField`. The JAR
  boot moved to `drivers/java-boot/ps1/_jar-boot.ps1`.
- The deploy-base secrets folder defaults to the primary API module's, not `backend`.
- Kit Python scripts speak UTF-8 on Windows pipes (`PYTHONUTF8=1`, child only).
- Driver, toolkit and CI READMEs link the kit's guides; the link test holds them. CLI help names
  `--mode remote` and `deliver`.

### The host run is declared too (ADR-001 amendment 6)

- `toolkit/hybrid/Invoke-HybridRun.ps1` names no driver. The `java-boot`, `node-vite` and
  `node-api` launch steps moved into each driver's declared `hybrid.script` (`ps1/hybrid.ps1`),
  as `dotnet-aspnet`'s already was; a driver without one is refused by name. `node-api` gains
  the `hybrid` delivery rung its launch step always had.
- `stack-kit hybrid boot <id>` runs the shared runner directly, not through the driver's `run`.
- A host run's environment is the resolver's rule (`envfile.HOST_RUN`: `.env.dev` over
  `.env.prod`; `resolve_cli.py run-env <folder>`; `Import-ModuleRunEnv`), not a fourth parser
  in the runner. An empty value in `.env.prod` no longer unsets a variable of the process.
- Layout floor: a declared `config.keys` and `vscode.cliScript` are rows; missing, they fail.
- `docs/INSTALL.md`: the hand-written launcher example used the advanced param block that
  loses `-d`; it now shows the simple one the scaffold ships.

### Delivery ladders by declaration (ADR-001 K6)

- Each driver declares its delivery ladder in `drivers/registry.json` `delivery`: rung →
  `{command, args}` (a driver command; `{environment}` substituted), `{via}` (a kit verb, e.g.
  `hybrid`) or `{pending}` (named, not built, with its reason). Declared today:

  | Driver | local | hybrid | remote-dev | release | container |
  |---|---|---|---|---|---|
  | java-boot | run | via hybrid | dev | deploy all | — |
  | node-vite | run | via hybrid | dev | deploy dist -Environment {environment} | — |
  | node-api | run | via hybrid | dev | deploy | — |
  | dotnet-aspnet | run | via hybrid | — | deploy artifact | pending: needs a docker host to prove it |

  The `release` rung is the one home of what `deployArgs` held (`stack-deploy` reads it; a project
  registry still saying `deployArgs` is read).
- `stack-kit mod <id> deliver <rung> [--env dev|prod] [--plan]` runs a rung, or prints its plan.
  An undeclared rung is refused, naming the declared ones; a pending rung is refused with its reason.
- `cli/stack-kit.ps1` names no driver. Its branches for two drivers' `watch`, `run` and
  `deploy` became declarations (`operands`: a word the driver rewrites, with its hint) and one
  generic dispatch. A `.sh` script runs under bash, a `.ps1` in the session, whatever the driver's
  `runtime` says. A PowerShell script's `-Name value` operands bind to the parameters it declares.
  A project driver (K7b) used to be dispatched by the kit registry's `runtime`; it is now
  dispatched by its own scripts.
- Off Windows, the CLI finds bash on PATH.

### A project may declare its own drivers (ADR-001 K7b)

- `drivers.registry` in the manifest names a project registry in the kit's shape. Its drivers
  live beside it (`<registry dir>/<id>/`) and are composed with the kit's by `lib/modules.py`,
  the one home of the composition. The resolver, driver dispatch, validate and every runtime
  see them.
- An id the kit already has is refused (`drivers: ... are the kit's`), never shadowed. The
  declared registry file is a layout-floor row.

### Configuration carries its sensitivity (ADR-001 K5)

- A host names its key catalogue in the manifest (`config.keys`). The kit owns its shape
  (`config/config-keys.schema.json`): per key `sensitivity` (SECRET, INTERNAL, PUBLIC), `owner`,
  `allowedSource`, `rotation` (required for SECRET), an optional non-secret `default`, extra
  `env` spellings; `knownExposures`; `orphans`.
- `validate` refuses a SECRET given a real value in any tracked env file, JSON or YAML: the key's
  path, or its environment spellings (`A:B` → `A__B`, `a.b` → `A_B`). A placeholder
  (`__NAME__`), an empty value or a `${...}` reference is not a value. A SECRET with a `default`
  or without a `rotation` is refused. A finding names file, place and key, never the value.
- An exposure already known is listed under `knownExposures` with the work that removes it. It
  is then printed on every validate instead of failing. Rotate first: the value is already in
  history.
- java-boot env-profile generation adds no integration of its own. The model, speech and cloud
  keys and the AI and `com.<consumer>.chat` loggers it rendered into every env-profiles module
  were one consumer's. A module declares its own block in `modules.<id>.configGen.profileYml`.

### Validation is a proof (ADR-001 K4)

- **The manifest schema is enforced on every machine.** `validate` used to hand
  `manifest.schema.json` to `jsonschema` when it happened to be installed and skip it otherwise,
  so on a host that had installed nothing every `required`, `enum` and
  `additionalProperties: false` was decoration. `lib/schema_check.py` interprets the schema's
  keywords itself and refuses any it cannot honour. A host may now see schema errors that were
  always there. A manifest on a former field name is validated under the current name.
- **`validate.stages`** declares the real-stack proof: `setup`, `migrate`, `build`, `test`,
  `health`, `ingest`, `anchor` and `teardown` stages, each an argv, fail-fast. Teardown always
  runs. An `anchor` compares its command's output (`equals`, `matches`, `atLeast`). A list with
  no anchor, or whose last working stage is not an anchor, is refused by plain `validate` before
  anything runs. Run it with `stack-kit validate --stages`.
- **Migrations are structure-only.** Each driver declares its migrations (`drivers/registry.json`
  `migrations`: globs, excluded generated files, data-statement patterns) for `java-boot`
  (Flyway SQL) and `dotnet-aspnet` (EF Core). `validate` names any migration that carries data.
  A module points elsewhere with `modules.<id>.migrations.paths`, and allows a reference-data
  file with `migrations.allowData: [{path, reason}]`.
- `cli/stack-kit.ps1` passed no arguments to `migrate`, `init` and `stack`: their handlers are
  invoked without arguments, so `@Args` was always empty, and `stack-kit migrate --apply` from
  PowerShell silently ran as a dry run. They pass the CLI's operands now, as does `validate`.

### The handwriting (ADR-001 K3)

- `.gitattributes` pins LF for every text file (CRLF only for `.cmd`/`.bat`). Under
  `core.autocrlf` a Windows checkout handed bash scripts CRLF, which fails on a Linux server.
- The host's tree is a declared layout held by `validate` as a floor (`lib/layout_floor.py`).
  Every place the manifest declares must exist (vendored kit, secrets root, module directories,
  declared compose catalog, CI scripts, infra compose directory once infra services are
  declared, nginx template). `layout.entries` adds rows in the agent kit's row shape;
  `layout.closed` names directories where an undeclared child is a failure. A `pending` row is
  printed, not failed.
- Tests are split into `tests/unit/` (in-process) and `tests/acceptance/` (shells and CLIs), and
  read the kit root and the fixture from `conftest.py` instead of computing their own.

### One resolver (ADR-001 K2)

Project discovery, manifest fields and their defaults, modules, roles, types, aliases, driver
lookup, env files and values, slugs, server and deploy paths, and the infra compose and tunnel
rules are answered by `lib/resolution.py` alone, through `lib/resolve_cli.py`. `lib/project.sh`,
`lib/env.sh`, `lib/drivers.sh`, `lib/project.ps1`, `lib/env.ps1`, `lib/drivers.ps1` and
`lib/modules.ps1` keep every public function and now only look answers up (1,485 lines of shell
resolution became 844, comments included). A shell resolves what the manifest says once and
keeps it; what the environment says is asked each time. Env files are read by one parser
(`lib/envfile.py`) instead of three.

The copies had drifted. Every runtime now gives the answer below; where a runtime used to
differ, it is named:

- **Project root:** a declared `STACK_KIT_PROJECT_ROOT` is authoritative; otherwise the working
  directory and its parents. PowerShell searched upward from the kit's own folder instead of the
  working directory; Python checked the working directory before the declared root.
- **Field defaults:** a missing field takes the declared convention default
  (`manifest_defaults.CONVENTION_DEFAULTS`), never an arbitrary template field. PowerShell applied
  no defaults at all (its `[string]$Default = $null` is `""`, so its template fallback never ran):
  a manifest without `secrets` gave PowerShell the project root as the secrets root.
- **A module's role:** declared, else the first role its driver declares. Bash spelled two
  drivers' roles inline.
- **An env value of a secrets folder:** the last non-empty value across `.env.dev`, `.env.prod`,
  `deploy.env`, `.env.deploy`, which is how compose applies them. Bash returned the first.
- **A shared deploy value:** the process environment first, then `deploy.env`. Bash read the file
  first.
- **The server base:** `DEPLOY_SERVER_BASE`, else `/home/<user>` from `DEPLOY_SERVER`, each looked
  up in `deploy.env` and then in every module folder. Bash looked only in `deploy.env`.
- **A remote deploy base with no `DEPLOY_PATH` and no server to derive one from:** refused.
  Bash produced `/<slug>/<folder>`; Python defaulted to `/home/deploy`.
- **The infra deploy path with neither:** refused. It used to be one consumer's server path.
- **CLI aliases, the UI compose service name, a driver's layout simulator:** the resolver's.
  PowerShell re-derived the aliases, took the UI service from a module literally named
  `frontend`, and mapped two driver names to simulators inline.

### Identity — the kit names no consumer (ADR-001 K1)

The package, command, manifest and environment are renamed; every former name is still READ for
the whole 1.x line, each read printing one line naming its replacement, once per process tree
(`STACK_KIT_NO_DEPRECATION_NOTICE=1` silences it). 2.0.0 stops reading them. All of it is declared
once, in `lib/identity.json`.

| Former | Current |
|---|---|
| package `geostat-kit`, vendored at `kits/geostat-kit` | `stack-kit`, `kits/stack-kit` |
| command `cli/geostat.ps1`, `cli/geostat.sh` | `cli/stack-kit.ps1`, `cli/stack-kit.sh` (the former paths remain as shims) |
| manifest `geostat.ops.json` | `stack-kit.json` |
| variables `GEOSTAT_*` | `STACK_KIT_*` — the same suffix, so `GEOSTAT_KIT_ROOT` is `STACK_KIT_KIT_ROOT` |
| manifest field `vscode.geostatScript` | `vscode.cliScript` |
| server marker `.geostat-deploy.json` | `.stack-kit-deploy.json` (a former marker is still found) |
| scaffolded launchers `tools/geostat.*`, `ops/cli/geostat.*` | `tools/stack-kit.*`, `ops/cli/stack-kit.*` |

**To move a host:** `stack-kit migrate` (dry run), then `stack-kit migrate --apply`. It renames the
manifest file and the renamed fields, refuses a host holding both manifest names, and PRINTS — never
rewrites — every line of the host's own files that still spells a former name.

Behaviour changes a host may notice:

- The variables are adopted inward only: a former variable set by an operator or CI is read; the kit
  no longer exports former names to the processes it starts.
- The java-boot pre-flight check names no integration of its own. A module declares what it checks in
  `modules.<id>.check.requiredEnv` / `optionalEnv` (the search, speech and model keys it used to
  name for one consumer's `chat-api` are gone).
- The primary API module is `stack.primaryApiModule` when declared, else the first module whose role is
  `api`; the module ids `backend` and `chat-api` are no longer privileged.
- Generated Spring defaults use the user `app` and password `app-dev-change-me` (were the consumer's
  name); the default database is `app`. Each remains overridable by its environment variable.
- `compose/build.py` and `compose/sync_ops_modules.py` resolve the project through the one discovery in
  `lib/project_context.py` instead of their own copies; `cli/stack-kit.sh` sources `lib/project.sh`.

### Agnosticism

- Reference test fixture is `tests/fixtures/golden-consumer/` with role-named,
  project-neutral module ids (`api`, `search`, `worker`, `web`, `svc`). No
  consumer brand appears in a fixture id, path or assertion.
- **Driver facts live in `drivers/registry.json`, not in generators.** Each driver
  declares `tasks` (e.g. `devWatch` argv) and `vscode.launch` (its launch shape).
  `lib/vscode_gen.py` no longer contains a `node-vite`/`java-boot` ladder or a
  privileged alias allow-list, so `node-api` — which previously got no VS Code
  tasks at all — now gets them by declaration. A new driver needs no generator edit.
- Role inference when a module omits `role` now reads the driver's declared
  `roles[0]` (`lib/modules.py`, `lib/drivers.ps1`) instead of a type→role ladder.
- `toolkit/deploy/pnpm-build.sh`: build ordering is declared as
  `modules.<id>.node.prebuildScripts` (default `[]`); no consumer script name lives
  in the kit. A declared script the workspace lacks now fails instead of silently
  skipping.
- `toolkit/dev/Invoke-DevUp.ps1`: help text renders from the resolved manifest's
  `cli.aliases` (placeholders when absent); remote watch uses the driver's declared
  `tasks.devWatch`; boot order is `dev.bootOrder` (default `api, worker, ui`).
- Spring actuator exposure is `modules.<id>.spring.managementEndpoints`, default the
  narrow `health,info`. A wider management surface is declared, never a kit default.
- `docs/DEV-MODES.md`, `docs/LOCAL-DEBUG.md`, `drivers/node-api/README.md` and the
  `node-vite` dev help use `<alias>` / `<moduleId>` placeholders only. The `node-api`
  README no longer claims the driver is unregistered.
- `lib/compose_identity.py`: the primary UI service name derives from
  role + primary-module resolution, not from a module literally named
  `frontend`; the privileged `backend` branch is removed.

### Capability

- `dotnet-aspnet` driver (registry entry, `_init.ps1`, `ps1/{run,hybrid,check,deploy}.ps1`):
  `run` through the shared hybrid runner, `check` pre-flight, `deploy artifact` =
  `dotnet publish` + declared `modules.<id>.dotnet.publishExpect` + `release.json`;
  `deploy remote` is an explicit refusal (delivery is not declared yet).
- **Hybrid run is declarative for new drivers.** `toolkit/hybrid/Invoke-HybridRun.ps1`'s
  `default` branch dot-sources the launch script a driver declares as
  `"hybrid": {"script": ...}` (`Get-DriverHybridScript` in `lib/drivers.ps1`) instead of
  refusing; the three existing rungs are unchanged.
- `lib/vscode_gen.py`: launch kind `dotnet` (C# Dev Kit `"type": "dotnet"`, project from
  `modules.<id>.dotnet.project` or the module's single `*.csproj`; ambiguity renders nothing).
- **`cli/geostat.ps1` no longer exits 0 when a PowerShell driver command fails** without
  setting `$LASTEXITCODE` (statement-terminating errors such as parameter binding). The
  PowerShell branch runs inside `try/catch` and exits 1 with the message. Proven by
  `TestCliReportsDriverFailure` (fails on the previous CLI).
- `validate` warns about `compose.catalog` only when the manifest declares `compose`.
- Manifest: `compose` is **optional** (schema `required` and `_validate_required`); a present
  `compose` without `catalog` is still refused. New module block `dotnet` (`project`,
  `launchProfile`, `configuration`, `publishExpect`).

- `node-api` driver (registry entry, `sh/`, `ps1/`, `_init.sh`).
- `geostat dev up` (`toolkit/dev/`), `resource_limits` / `extraServices`
  compose seams, `manifest.migration.legacyDirs`.

## 1.0.0 — 2026-05-21

### Adoption

- [docs/ADOPTION.md](docs/ADOPTION.md) — გავრცელება, რა გავაკეთეთ, GitHub topics, submodule pin

### Documentation & tooling

- [docs/DEV-MODES.md](docs/DEV-MODES.md) + `scripts/dev-modes-verify.*` — dev mode smoke
- [docs/LOCAL-DEBUG.md](docs/LOCAL-DEBUG.md) + `lib/vscode_gen.py` — Run and Debug from manifest

### Package boundary (manifest-driven)

- N-module model: `modules.*.role`, `path`, `secretsModule`, dynamic CLI/layout
- Single default source: `scaffold/geostat.ops.json` via `lib/manifest_defaults.py`
- Runtime hardcode ban: `test_toolkit_hardcodes.py`
- Project CI: consumer `ops/ci/integration-stack.sh` resolves api module from manifest

### Credentials

- Per-module `modules.<id>.credentials[]` (multi-file / multi envVar)
- Global fallback: `features.gcpCredentials` + `adapters.gcp.*`
- `dev-remote`, `ci_prepare`, `upload` use resolved credential profiles

### Tooling

- `geostat validate` — schema + project checks
- `geostat migrate` — v2 role/secretsModule hints (`--apply`)
- Golden consumer fixture: `tests/fixtures/golden-consumer/`

### Docs

- `docs/MATURITY.md`, `docs/STARTER.md`, `docs/PACKAGE-ARCHITECTURE.md` (CI/credentials)
