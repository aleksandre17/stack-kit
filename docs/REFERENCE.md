---
kind: guide
authority: canonical
owns: reference
---

# stack-kit reference

The manifest, the commands, the drivers, the tree and the resolver. Where a file is the authority
it is named and not copied: `manifest.schema.json` (manifest), `drivers/registry.json` +
`drivers/registry.schema.json` (drivers), `lib/identity.json` (names), `cli/stack-kit.ps1` /
`cli/stack-kit.sh` (verbs). Boundaries: [ARCHITECTURE.md](../ARCHITECTURE.md). Why: [decisions/](decisions/).

## Principles

| Principle | Meaning |
|---|---|
| Agnostic | No driver assumes postgres, redis or any named app; no consumer name in the kit (boundary test) |
| Open/closed | Extend by manifest + host compose files; a new store or driver needs no kit edit |
| Single responsibility | Kit = run, sync, paths, CLI; host = which services exist |
| Manifest contract | `stack-kit.json` declares intent; no env toggle duplicates a manifest selection |
| Declared, not inferred | Driver facts (roles, watch tasks, launch kind, deploy args) live in the registry; generators carry no driver ladder |

Not used, by design — reject in review:

- env-based service toggles (`INFRA_PROFILES`); hardcoded `frontend`/`backend` URLs or module ids in the kit runner;
- a fixed api/app/worker triple or a fixed postgres/redis/qdrant set; a single API URL in `integration-stack.sh` when N modules exist;
- every module name repeated in `deploy.env` when the manifest declares `target`/`role`;
- host repo paths, product aliases or dev-mode labels in kit runtime strings; inline `DEFAULTS = {...}` dicts;
- a monolithic compose every host must use as-is.

## Package tree

| Path | Holds |
|---|---|
| `cli/` | `stack-kit.ps1` (every verb), `stack-kit.sh` (bash verbs, delegates the rest); the former command names remain as shims (`lib/identity.json` `legacyKitName`) |
| `lib/` | the resolver (`resolution.py`, `resolve_cli.py`, `envfile.py`, `identity.py` + `identity.json`), manifest/defaults (`project_context.py`, `manifest_defaults.py`, `modules.py`, `modules_cli.py`, `driver_api.py`), feature logic (`validate_manifest.py`, `migrate_manifest.py`, `migrate_identity.py`, `vscode_gen.py`, `config_gen.py`, `ci_prepare.py`, `ci_health.py`, `credentials.py`, `compose_identity.py`, `deploy_paths.py`, `stack_deploy.py`, `stack_endpoints.py`, `infra_tunnel.py`), shell shims (`project.*`, `env.*`, `drivers.*`, `modules.ps1`, `ssh.*`, `module-manifest.ps1`, `stack-kit-python.ps1`), `deploy-defaults.json` |
| `toolkit/` | shared operations: `bash/`, `powershell/` (SSH, compose, logs, static watch, remote dev), `deploy/` (upload, JAR prep, deploy watch, dev remote, stack-remote, layout migrate/cleanup), `dev/` (`dev up`), `hybrid/`, `infra/`, `init/`, `layout/` (simulators), `stack/`, `templates/` (`ops.config.*.example`) |
| `drivers/` | one folder per stack type + `registry.json`; `_template/` to copy |
| `compose/` | generator (`build.py`, `build.ps1`, `build.sh`, `manifest_compose.py`, `sync_ops_modules.py`) and catalogs: `compose-catalog.json` (templates per `type` + `role`), `stack-catalog.json` (per-role port env keys, defaults, health `urlPath`, `healthExpect`, `ciHealth`), `infra-catalog.json` (reference infra modules + tunnel port keys) |
| `config/` | `config-gen` entry (`build.py`) and `config-catalog.json` (profile boilerplate) |
| `adapters/` | `render_nginx.py` (`nginx-gen`) |
| `ci/` | generic CI helpers: `prepare-integration-env.sh`, `wait-health.sh`, `wait-stack-health.sh` |
| `contracts/` | manage/log contracts ([MANAGE-CONTRACT.md](../contracts/MANAGE-CONTRACT.md)) |
| `scaffold/` | everything `init` copies into a host ([scaffold/README.md](../scaffold/README.md)) |
| `scripts/` | `dev-modes-verify.*`, `module-ops-smoke.sh`, `publish-git.ps1` |
| `tests/` | `unit/` (in-process), `acceptance/` (shells and CLIs), `fixtures/golden-consumer/` ([tests/README.md](../tests/README.md)) |
| `docs/` | these four guides + `decisions/` |

Never in the kit: a real `DEPLOY_SERVER`, API keys, production CSP domains, generated `docker-compose*.yml`, business code, consumer health URLs.

## Manifest

`stack-kit.json` at the host root. **Authority: [manifest.schema.json](../manifest.schema.json)**; example: [scaffold/stack-kit.json](../scaffold/stack-kit.json).
Required: `version` (integer ≥ 2), `package`, `secrets`, `modules`.

| Section | Declares |
|---|---|
| `version` | manifest format; `migrate` raises older ones to 2 |
| `package` | kit path from the root (`kits/stack-kit`) |
| `secrets` | config root (`ops/config`) |
| `compose` | optional; `catalog` (required when `compose` is present), `syncModules` (java-boot `ops.modules`) |
| `stack` | `composeDir`, `infraComposeDir`, `networkName`, `primaryApiModule` (default: first `api` module), `composeModules` (compose-gen + stack-deploy list; default all), `deployBaseSecretsModule` (shared `DEPLOY_PATH`/`DEPLOY_LAYOUT`; workers inherit it when their `.env.deploy` omits `DEPLOY_PATH`), `modules` (filter for `stack up` endpoint hints only), `composeNaming`, `infra.services` (`services/<id>.yml` merged with `docker-compose.base.yml`), `infra.composeFiles` (full `-f` override) |
| `cli.aliases` | shortcut → module id |
| `stackDeploy` | `modules` (override list), `steps` (explicit; only when the auto plan is insufficient) |
| `modules.<id>` | see below |
| `vscode` | `folder`, `cliScript` (default `tools/stack-kit.ps1`), `hybrid.{compoundName,apiModule,uiModule,preLaunchTask}` |
| `dev.bootOrder` | roles in `dev up all` order; default `["api","worker","ui"]` |
| `migration.legacyDirs` | one-time layout-migration inputs |
| `features` | booleans the kit reads, e.g. `gcpCredentials` |
| `adapters` | `gcp.{credentialsFile,containerMount,envVar}`, `nginx.{template,output,envExample,env}`, `embed.envExample` |
| `validate.stages` | the real-stack proof `validate --stages` runs: stages `{id, kind, run, cwd, env, timeout, expect}`, kind `setup`, `migrate`, `build`, `test`, `health`, `ingest`, `anchor`, `teardown`; fail-fast, teardown always runs; an `anchor` compares stripped stdout (`expect.equals` \| `matches` \| `atLeast`); a list without an anchor, or whose last working stage is not one, is refused (`lib/pipeline.py`) |
| `layout` | the host tree as a declared layout held by `validate` as a floor (`lib/layout_floor.py`): `entries[]` `{path, kind, holds, writer, read_when, lifecycle, pending}` add rows to the places the manifest already declares; `closed` names directories where an undeclared child fails; a `pending` row is printed, not failed |
| `ci` | `integration`, `prepareEnv`, `waitHealth`, `waitStackHealth`, `healthModules` (subset of health targets) and further host script paths (see the schema) |

`modules.<id>` — required `type`, `role`, `path`, `secretsModule`:

| Field | Declares |
|---|---|
| `type` | driver id from `drivers/registry.json` |
| `role` | `ui`, `api`, `worker`, `gateway`, `data`, `other` — stack order, layout, shortcuts |
| `path` | app source dir (`apps/backend`) |
| `secretsModule` | folder under `secrets` |
| `target` | compose service slug (`search` → `<slug>-search`); not a server path |
| `credentials[]` | `{file, mount, envVar}` files under `secretsModule`; overrides the global GCP profile for this module |
| `check.{requiredEnv,optionalEnv}` | env the pre-flight check requires / reports |
| `compose.embeddedWorker` | legacy `worker/` sidecar next to the primary api |
| `debug` | VS Code: `label`, `npmScript`, `envFile`, `mainClass`, `projectName`, `java.{mainClass,projectName}` |
| `hybrid` | `springProfiles`, `gradleWrapper`, `gradleProject`, `npmScript`, `preferJar`, `bootJar` |
| `spring`, `datastores` | `config-gen` inputs (profiles, `managementEndpoints` default `health,info`, postgres schema …) |
| `node.prebuildScripts` | pnpm build ordering (default `[]`; a declared script the workspace lacks fails) |
| `dotnet` | `project`, `launchProfile`, `configuration` (default `Release`), `publishExpect` |
| `migrations` | `paths` (migration dirs outside the module tree), `allowData[]` `{path, reason}` (reference-data files allowed); migrations are structure-only and `validate` names any that carries data (`lib/migrations_gate.py`, driver `migrations` patterns) |
| `scripts` | deprecated |

Convention defaults: a missing field takes its value from `scaffold/stack-kit.json`, for the declared
list `manifest_defaults.CONVENTION_DEFAULTS` only (`package`, `secrets`, `compose.*`, `stack.composeDir`,
`stack.infraComposeDir`, `stack.networkName`, `adapters.*` paths, `ci.*` helper paths, `vscode.*`) —
never a sample module or alias of the template.

Credentials (`lib/credentials.py` `module_credentials(manifest, moduleId)`): a module's `credentials[]`
wins; else, with `features.gcpCredentials: true`, the global `adapters.gcp` profile.

```json
"features": { "gcpCredentials": true },
"adapters": { "gcp": { "credentialsFile": "google-credentials.json", "containerMount": "/app/google-credentials.json", "envVar": "GOOGLE_APPLICATION_CREDENTIALS" } },
"modules": { "api": { "role": "api", "type": "java-boot", "path": "apps/api", "secretsModule": "api",
  "credentials": [
    { "file": "gcp-primary.json", "mount": "/app/gcp-primary.json", "envVar": "GOOGLE_APPLICATION_CREDENTIALS" },
    { "file": "gcp-audit.json", "mount": "/app/gcp-audit.json", "envVar": "GCP_AUDIT_CREDENTIALS" } ] } }
```

Derived rules:

| Rule | Source |
|---|---|
| Compose service names: primary api `{slug}-api`, primary ui `{slug}-app`, others `{slug}-{target or id}`; `slug` = `COMPOSE_PROJECT_NAME` or repo folder; `deploy.env` `COMPOSE_API_SERVICE` / `COMPOSE_APP_SERVICE` / `COMPOSE_WORKER_SERVICE` are legacy overrides only | `lib/compose_identity.py` |
| Stack deploy plan (no `stackDeploy.steps`): modules of `stack.composeModules` (or `stackDeploy.modules`) in role order api → worker → gateway → data → ui → other; args from the driver's `deployArgs` (java-boot `deploy all`, node-vite `deploy dist -Environment {environment}`); `{environment}` → `dev`/`prod`; `--dev`/`--prod` appended | `lib/stack_deploy.py` |
| CI health: one probe per module of `stack.composeModules` (or `ci.healthModules`), URL from the role in `stack-catalog.json` | `lib/ci_health.py` |
| Embedded worker vs `role: worker` module: never both for one job | `compose_identity.effective_compose_features` |
| Infra: services = `stack.infra.services`; tunnel port keys from `compose/infra-catalog.json` (+ optional host `ops/compose/infra/infra-catalog.json`) | `lib/infra_tunnel.py` |
| Adding a data store: `ops/compose/infra/services/<store>.yml` + `"<store>"` in `stack.infra.services`; no kit release | — |

## Commands

`stack-kit <verb>` (PowerShell: `.\tools\stack-kit.ps1 <verb>`). Which runtime runs which verb: [INSTALL.md#launchers](INSTALL.md#launchers).

| Verb | Does | Implementation |
|---|---|---|
| `help` | verbs, driver types, project modules with role/type/capabilities, aliases | `cli/stack-kit.ps1` |
| `init [flags]` | bootstrap ([ADOPT.md#bootstrap-with-init](ADOPT.md#bootstrap-with-init)) | `toolkit/init/` |
| `validate [--stages]` | schema (enforced by `lib/schema_check.py`, no `jsonschema` needed) + project checks + layout floor + migrations gate; `--stages` runs `validate.stages` | `lib/validate_manifest.py` |
| `migrate [--apply]` | dry run / apply manifest + identity migration | `lib/migrate_manifest.py` |
| `vscode-gen [--force]` | `.vscode/launch.json` + `tasks.json`; missing files only unless `--force` | `lib/vscode_gen.py` |
| `config-gen [<moduleId>] [--all] [--check] [--dry-run]` | Spring `application*.yml` boilerplate; `validate` reports drift; never touches `application-custom.yml` (PowerShell only) | `lib/config_gen.py`, `config/config-catalog.json` |
| `compose-gen` | catalog + manifest (`stack.composeModules`) → `docker-compose*.yml`, `ops.modules` | `compose/build.ps1` / `compose/build.py` |
| `nginx-gen` | `adapters.nginx.template` → output | `adapters/render_nginx.py` |
| `stack [-Prod] <compose args>` | `docker compose` in `stack.composeDir` with stack env files; prints endpoint lines | `toolkit/stack/compose.ps1` / `compose.sh` |
| `stack-deploy [--dev\|--prod] [--no-build] [--skip-checks]` | remote full stack (default `--prod`) | `toolkit/deploy/stack-remote.sh` |
| `infra` | no arguments: SSH checks + Docker network | `toolkit/infra/ensure-prereqs.sh` |
| `infra prereqs \| local up\|down\|status \| remote sync\|up\|down\|status\|purge \| tunnel` `[-Prod] [-Confirm]` | infra compose locally or on the server; `remote sync` rsyncs `stack.infraComposeDir` to `{infra deploy path}/compose/`, `remote up` syncs then starts; `purge -Confirm` = `down -v` for this `INFRA_SLUG` only; `tunnel` = `ssh -L` for `stack.infra.services` | `toolkit/infra/Invoke-Infra.ps1` ([README](../toolkit/infra/README.md)) |
| `layout [--all] [--role <r>] [--module <id>] [--no-server] [-Markdown -OutFile <f>]` | dry-run server layout per module + server overview (`--frontend`/`--backend` deprecated → `--role ui`/`--role api`) | `toolkit/layout/` |
| `layout migrate\|cleanup [--dry-run] [--dev\|--prod] [--backend\|--frontend\|--all]` | flat → structured on the server / remove this host's old dirs (`cleanup --legacy-segments`) | `toolkit/deploy/migrate-layout.sh`, `cleanup-scoped-layout.sh` |
| `hybrid boot <alias\|moduleId>` | host run with the module's `.env.dev` over its `.env.prod` (same as `<alias> run`) | `toolkit/hybrid/Invoke-HybridRun.ps1`, then the driver's declared `hybrid.script` |
| `dev up <alias\|moduleId\|all> [--mode hybrid\|local\|docker\|remote] [--no-infra] [--no-tunnel]` | dev orchestration ([GOLDEN-PATHS.md#dev-modes](GOLDEN-PATHS.md#dev-modes)) | `toolkit/dev/Invoke-DevUp.ps1` |
| `mod <moduleId> <command> [args]` | a module's driver command (canonical form; default command `deploy`) | the driver |
| `<alias> <command> [args]` | same, through `cli.aliases` or a role shortcut | the driver |

Module commands are the driver's `commands` in the registry (table in [Drivers](#drivers)). CLI routing:

- `<node-vite> watch` → `deploy watch` (hint printed); `<java-boot> watch` → `dev watch` (hint printed).
- `<java-boot> deploy watch` → JAR publish loop (`toolkit/deploy/deploy-watch.sh`).
- `<node-vite> deploy <local|dist|remote|sync|watch> [-Environment dev|prod]` (default `prod`).
- `<node-vite> dev <bootstrap|sync|watch|restart>`; `<node-vite> compose [-Prod] <args>`.
- `<java-boot> deploy [service|all] [--dev|--prod] [--no-build] [--skip-checks]`; `dev <bootstrap|sync|watch|restart> [--no-build] [--no-initial-sync] [--restart]`; `manage <svc> <action> [--prod]` ([contract](../contracts/MANAGE-CONTRACT.md)); `modules`.
- A bash-runtime driver needs Git Bash on Windows; a PowerShell driver that throws exits 1 with the message.
- Role shortcuts: `ui`, `api`, `worker`, `gateway` resolve to the module when exactly one module has that role and no alias of that name exists.

Inspect (Python, from the kit with `PYTHONPATH` = kit root): `lib/driver_api.py list-types`;
`lib/modules_cli.py compose-names` (JSON) | `stack-deploy-steps [dev|prod]` | `stack-health` (TSV module, url, expect) | `stack-endpoints` | `aliases` | `role <id>` | `by-role <role>`.

## Environment variables

| Variable | Meaning |
|---|---|
| `STACK_KIT_PROJECT_ROOT` | host root; authoritative when set; the CLI exports it |
| `STACK_KIT_KIT_ROOT` | kit root; the CLI exports it |
| `STACK_KIT_MODULE_ID` | module the driver runs for; set by the CLI |
| `STACK_KIT_MONOREPO_ROOT` (or `OPS_MONOREPO_ROOT`) | monorepo root for slugs and extra sync paths; default the host root |
| `STACK_KIT_LEGACY_ROOT_DISCOVERY=1` | allow pre-v2 root discovery ([ADOPT.md#moving-an-existing-host](ADOPT.md#moving-an-existing-host)) |
| `STACK_KIT_NO_DEPRECATION_NOTICE=1` | silence former-name notices |
| `STACK_KIT_NOTICED` | internal: notices already given in this process tree |
| `STACK_KIT_HYBRID_JAR=1` / `STACK_KIT_HYBRID_GRADLE=1` | force JAR / Gradle boot in hybrid run (default: `hybrid.preferJar`, else JAR on Windows) |
| `STACK_KIT_DOCKER_NETWORK` | `deploy.env` alternative to `DOCKER_NETWORK` |

Former-prefix variables (`lib/identity.json` `legacyEnvPrefix`) are adopted inward to `STACK_KIT_*` (current wins) until 2.0.0 ([CHANGELOG.md](../CHANGELOG.md) 1.2.0-dev). `deploy.env` and module env keys: [ADOPT.md#configuration](ADOPT.md#configuration), [GOLDEN-PATHS.md#server-layout](GOLDEN-PATHS.md#server-layout).

## Drivers

**Authority: [drivers/registry.json](../drivers/registry.json)** (schema `drivers/registry.schema.json`). Type = toolchain; module id = host key; a module always names its `type`.

| Type | Roles | Runtime | Commands | Watch tasks | Launch | Deploy kind / args |
|---|---|---|---|---|---|---|
| `java-boot` | api, worker | bash | deploy, dev, run, manage, compose, check, modules | `devWatch` | java | runtime / `all` |
| `node-vite` | ui | powershell | deploy, dev, run, manage, compose, check | `devWatch`, `deployWatch` | node-terminal | static / `dist -Environment {environment}` |
| `node-api` | api | bash | deploy, dev, run, manage, compose, check, modules | `devWatch` | node-terminal | runtime |
| `dotnet-aspnet` | api | powershell | deploy, run, check | — | dotnet | artifact / `artifact` (`deploy remote` refused: delivery not declared) |

Per-driver detail: [java-boot](../drivers/java-boot/README.md), [node-vite](../drivers/node-vite/README.md), [node-api](../drivers/node-api/README.md), [dotnet-aspnet](../drivers/dotnet-aspnet/README.md), [drivers/README.md](../drivers/README.md).

Entry fields: `label`, `roles` (first = default role), `runtime` (`bash` | `powershell`), `commands`
(name → script), `tasks` (`devWatch`, `deployWatch` argv; `dev up --mode remote` and `vscode-gen` read them),
`vscode.launch`, `deployKind`, `deployArgs`, `layoutSimulator`, `hybrid.script` (the launch step the hybrid
runner dot-sources; a `hybrid` rung requires it), `migrations` (`globs`, `exclude`, `data` patterns; java-boot Flyway SQL, dotnet-aspnet EF Core), `configGen`, `acceptsGlobalCredentials`. A driver that declares no watch task gets none — a declared absence.

Adding a driver (Go, FastAPI, Next.js, a Node API …) — a new type, never a renamed folder:

1. Copy `drivers/_template/` → `drivers/<type>/` (name = registry key).
2. Implement `_init.sh` or `_init.ps1` (`STACK_KIT_MODULE_ID`, `ops.config`, toolkit `_common`) and the commands you need: `deploy` (artifact → SSH → server compose), `manage` (stop/start/logs/status), `compose` (local compose + env files), `check` (prereqs, build smoke). Reuse `toolkit/`; do not copy SSH/env logic into the driver.
3. Register it in `drivers/registry.json` (`label`, `roles`, `runtime`, `commands`, plus `tasks`/`vscode` to get watch tasks and a launch config).
4. Point the module at it: `"type": "<type>"`; add the service to `ops/compose/catalog.json`; adjust `stackDeploy.steps` only if the auto plan does not fit.
5. `stack-kit help`, `stack-kit mod <id> check`, `stack-kit mod <id> deploy … --prod`.

Several APIs in one host are several modules with their own types, e.g. `legacy-api` → `java-boot`,
`gateway` → `node-api` (`stack-kit mod gateway deploy --prod`). `node-vite` (UI, static `dist`, nginx) and
`node-api` (HTTP service, image) never share a driver.

## Resolver

One resolver (ADR-001 decision 2): `lib/resolution.py` answers manifest reading, project discovery,
field defaults, modules/roles/types/aliases, driver lookup, env files and values, slugs, server and
deploy paths, and the infra compose and tunnel rules. Shells ask it through `lib/resolve_cli.py`;
`lib/project.sh`, `env.sh`, `drivers.sh`, `project.ps1`, `env.ps1`, `drivers.ps1`, `modules.ps1` keep
their public functions and hold no rule (`tests/acceptance/test_resolver_parity.py`). Env files are parsed only by `lib/envfile.py`.

| Question | Answer |
|---|---|
| Project root | `STACK_KIT_PROJECT_ROOT` if set; else the working directory and its parents holding `stack-kit.json`; else (opt-in) legacy discovery |
| Missing field | its convention default ([Manifest](#manifest)) |
| Module role | declared, else the driver's first role |
| Env value of a secrets folder | last non-empty across `.env.dev`, `.env.prod`, `deploy.env`, `.env.deploy` (compose semantics) |
| Shared deploy value | process environment, then `deploy.env` |
| Server base | `DEPLOY_SERVER_BASE`, else `/home/<user>` from `DEPLOY_SERVER` (`deploy.env`, then every module folder) |
| Remote deploy base of a folder | its `DEPLOY_PATH`, else `{server base}/{DEPLOY_PROJECT slug}/{folder}`; neither → refused |
| Infra deploy path | `ops/config/infra` `DEPLOY_PATH` (must end `/infra/{INFRA_SLUG}`), else `{server base}/{DEPLOY_PROJECT}/infra/{INFRA_SLUG}`; neither → refused. `INFRA_SLUG` default: repo folder |

`resolve_cli.py [--shell bash|pwsh] <verb>`: `context` (bash: shell to `eval`; PowerShell: one JSON
document), `notice`, `env-files <folder> [dev|prod|deploy|all]`, `env-value <folder> <KEY> [default]`,
`deploy-env-value <KEY> [default]`, `project-slug`, `compose-slug`, `docker-network`, `server-base`,
`infra-slug`, `infra-deploy-path`, `deploy-base <folder>`, `infra-services`, `infra-compose-files`,
`infra-compose-args`, `infra-sync-paths`, `infra-tunnel-forwards`, `slugify <text>`, `alias <alias>`.
A shell caches `context` (what the manifest says) for its lifetime and asks the environment's answers each
time; secret values never enter the context. `--shell bash` on Windows prints paths as Git Bash spells
them (`/c/...`); output is LF, UTF-8.

Library entry points (all answered by the resolver):

| Runtime | Examples |
|---|---|
| Python | `from lib.project_context import ProjectContext`; `ctx = ProjectContext.discover()`; `ctx.secrets_module_dir("<moduleId>")`, `ctx.module_id_for_type("node-vite")`, `ctx.resolve_alias("fe")`, `ctx.compose_service_names()`; `lib.manifest_defaults.default_field()`, `flatten_defaults()` |
| Bash (`source lib/project.sh`) | `stack_kit_find_project_root`, `stack_kit_read_manifest_field <field> [default]`, `stack_kit_module_id_for_role api`, `stack_kit_module_id_for_type node-vite`, `stack_kit_module_path <id>`, `stack_kit_secrets_dir_for_module <id>`, `stack_kit_default_remote_deploy_base "$(stack_kit_secrets_module_name <id>)"` |
| PowerShell (`. lib\project.ps1`) | `Get-ProjectRootFromManifest`, `Get-ManifestField`, `Get-ManifestModulePath (Get-ModuleIdByDriverType node-vite)`, `Get-DefaultRemoteDeployPathBase -SecretsFolder (Get-ModuleSecretsFolder <id>)`, `Resolve-CliAlias fe` (`lib\drivers.ps1`) |
