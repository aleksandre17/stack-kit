---
kind: guide
authority: canonical
owns: reference
---

# stack-kit reference

The manifest, the targets, the layout, the drivers and the resolver. Where a file is the authority
it is named and not copied: `manifest.schema.json` (manifest), `config/deploy-targets.schema.json`
(targets), `config/deploy-layout.default.json` (layout), `drivers/registry.json` +
`drivers/registry.schema.json` (drivers), `config/catalogs/` (roles, tiers, environments, lifecycle
steps, target runtimes), `lib/identity.json` (names). The verbs: [OPERATIONS.md](OPERATIONS.md),
generated from the CLI's registry. Boundaries: [ARCHITECTURE.md](../ARCHITECTURE.md). Why: [decisions/](decisions/).

## Principles

| Principle | Meaning |
|---|---|
| One home per fact | every name from `lib/naming.py`, every remote path from `lib/targets/layout.py`, every command line of a tool from its declaration; a former home (deploy.env, `.env.deploy`, DEPLOY_*/COMPOSE_* keys) is a `validate` error naming `migrate` |
| Declared, not inferred | a driver declares its build, package, container recipe, dev container and reactions; the generic pipeline names no tool (`tests/unit/test_one_home.py`) |
| Open/closed | a driver, tier, environment, lifecycle step or target runtime is a declaration (a project registry, `catalogs.*`), never a kit edit (`tests/unit/test_delivery_engine.py` runs on a driver the kit does not ship) |
| Plan before acting | every remote verb prints its plan; `--plan` stops there; nothing acts on the shared root |

## Package tree

| Path | Holds |
|---|---|
| `cli/` | `stack_kit.py` (the entry point), `stack-kit.ps1` and `stack-kit.sh` (launchers that only find Python) |
| `lib/cli/` | the operator CLI: `main.py`, `registry.py` (verbs, options, exit codes, the generated docs), `verbs/` (one module per verb), `remote.py` (plan, confirm, act), `tools.py` (driver commands by runtime, the run record) |
| `lib/delivery/` | the engine: `context.py`, `transport.py` (ssh, a local directory, a recording fake, a plan), `model.py` (a service from its declarations), `stack.py` (the environment's compose file), `running.py`, `release.py`, `preflight.py`, `consumes.py` (what a shared platform provides), `tree.py` (init, verify), `drift.py`, `dev.py` + `sync.py` (remote dev), `manage.py`, `infra.py`, `legacy_layout.py`, `fake_server.py` |
| `lib/targets/` | `declaration.py` (load, select, validate), `layout.py` (the one renderer of remote paths), `remote.py` (ssh, engine and compose invocations) |
| `lib/resolution/` | `context.py` (what the manifest says, flat), `resolver.py` (env files and values, the selected target), `infra.py` (the local infra stack) |
| `lib/` | `naming.py`, `templating.py`, `package.py`, `catalogs.py`, `modules.py` (the driver registry), `project_root.py`, `project_context.py`, `legacy.py` + `migrate_legacy.py` (the former homes), generators (`ci_gen.py`, `vscode_gen.py`, `config_gen.py`), `validate_manifest.py`, shell shims over `resolve_cli.py` (`project.*`, `env.*`, `drivers.ps1`, `modules.ps1`) |
| `drivers/` | one folder per driver (its scripts and `container/` recipes) + `registry.json`; `_shared/` (runners a driver family shares); `_template/` |
| `toolkit/` | what runs on this machine: `dev/` (local dev modes), `hybrid/` (the host run), `infra/` (the local infra stack), `init/` |
| `compose/` | the local compose generator (`compose-gen`) and its catalogs |
| `config/` | catalogs, the default layout, the delivery defaults, the targets schema, the runtimes of scripts |
| `adapters/`, `ci/`, `scaffold/`, `scripts/` | nginx-gen; CI helpers; what `init` copies into a host; kit maintenance |

## Manifest

`stack-kit.json` at the host root. **Authority: [manifest.schema.json](../manifest.schema.json)**; example: [scaffold/stack-kit.json](../scaffold/stack-kit.json).

| Section | Declares |
|---|---|
| `project` | the project's one name: its directory on a target, its compose projects, containers, networks, volumes, local services (default: the repository folder) |
| `package`, `secrets` | the kit's path; the config root (`ops/config`) |
| `modules.<id>` | `type` (a driver), `role`, `path`, `secretsModule`; `container` and `services` (over the driver's), `dev` (over the driver's), `runtimeConfig[]` `{from, to, environments, mount}`, `credentials[]` `{file, mount, envVar}`, `credentialPatterns`, `toolchain.version`, the driver's own fields (`dotnet`, `node`, `hybrid`, ...), `extensions` |
| `stack.services` | services no module builds (an object store, a cache): `image`, `tier`, the service vocabulary |
| `stack` | the local stack: `composeDir`, `infraComposeDir`, `primaryApiModule`, `composeModules`, `infra.services` |
| `deploy.targets` | the tracked targets file (below) |
| `consumes` | what the project uses from a shared platform it does not own ([lib/delivery/consumes.py](../lib/delivery/consumes.py)): `networks` {name: {`services`, `owner`}} joined as external, never created or removed, read by the preflight (a missing one is NOT RUN with its owner's action); `endpoints` {name: {`env`, `services`, `owner`}} given as that variable; `routes` [{`environment`, `host`, `path`, `service`, `port`, `network`, `tls`: `required`}] rendered by `render` to `projections.routes` (default `ops/compose/stack/<env>/edge-routes.json`) for the platform's owner to apply |
| `catalogs` | the host's entries over `config/catalogs/` (`roles`, `tiers`, `environments`, `lifecycle`, `targetRuntimes`); a new id goes `after` the one it names |
| `drivers.registry` | the project's own drivers, beside their registry |
| `runtimes` | the host's script runtimes over `config/runtimes.json` |
| `commands`, `ci`, `vscode`, `layout`, `validate.stages`, `config`, `features`, `adapters` | as the schema says |

A service's declaration has one vocabulary at every level (driver `container`, module `container`,
module `services.<id>`, `stack.services.<id>`), a later level winning: `template`, `dockerfile`,
`image`, `port`, `command`, `entry`,
`healthcheck` (compose form), `environment`, `volumes` {name: mount}, `logs`, `serve`, `dependsOn`,
`healthWait`, `keep`, `context`, `artifact`, `artifactExclude`, `networks`, `healthPath` (the recipe's HEALTHCHECK asks it; without one, the port answering), `proxy` {path: service} (a static app's same-origin reverse proxy), `builtChecks` / `allowBaked` (a built app carries no `http://` URL or IP literal), `generatedSecrets` {`directoryEnv`, `uid`, `reads` {glob (one or a list), pattern (`@env@`: each key's env name), how, `built` {glob, pattern}}} (the driver's alone, unless the module builds from its own `dockerfile`: how the runtime reads a generated secret, the uid its image runs as, and what reading it looks like in code and in what a release carries -- validate refuses a module given one its source never reads or whose driver declares no `reads`, a release one its built output never reads, a rollback one on the server). Every image a release runs names a version (never `latest`), and a digest where the environment declares `requireDigests`. Remote dev: `image`,
`command`, `build`, `port`, `debugPort`, `caches` {name: mount}, `excludes`, `reactions`
[{`globs`, `do`: hot-reload | restart | rebuild}], `environment`, `debounceMs`, and a driver's
`projectReferences` capability (dotnet-aspnet follows the selected project's in-root MSBuild references).

## Targets

`deploy.targets` names a tracked, non-secret file (schema `config/deploy-targets.schema.json`),
merged under a gitignored `<name>.local.json`. Per target: `runtime` (catalogs.targetRuntimes:
`docker-compose`, `static`, `iis` pending), `host`, `user`, `port`, `root` (the directory the
platform shares; this project's own is `{root}/{project}`), `ssh` {`identity`: `agent` | `env:VAR` |
`file:<ignored path>`, `knownHosts`, `hostKeys` `pinned` | `accept-new`, `config`, `options`},
`compose` / `engine` (this host's invocations over the runtime's), `layout`, `ports`
{environment: {service: [host ports]}}, `health` {environment: {service: url}}, `keep`,
`healthWait`, `minFreeMb`, `legacyLayout` {`environment`, `units`, `places`}, `pending`, `runner`,
`consumes` {`networks` {name: its name on this host}, `endpoints` {name: {environment: address}}};
top-level `defaults` {environment: target}.

## Layout

`config/deploy-layout.default.json`: `project` `{root}/{project}`, `environment`, `unit`
`{environment}/{tier}/{service}`, `releases`, `current`, `logs`, `runtime`, `workspace`, `stack`,
`stackCompose`, `stackEnv`, `stackState`, `infra`, `backups`; `unproven` names what is not yet proven
(a real docker host). A target's `layout` overrides any template; every rendered path lies strictly
under `{root}/{project}`, refused otherwise (`lib/targets/layout.py`).

## Drivers

**Authority: [drivers/registry.json](../drivers/registry.json).** A driver declares `label`, `roles`,
`commands` (script, or `{script, runtime}`), `packageScripts`, `hybrid.script`, `package`
`{command, args, artifacts}` (`{out}`: the staging directory), `container` (above), `dev` (above),
`outputs` (what its toolchain writes, gitignore-style, relative to the module; validate refuses a tracked match, a module adds its own in `modules.<id>.outputs`), `delivery` (rung -> `{via}` a kit verb, `{command, args}`,
or `{pending}`), `health` (`expect: status`, `pathRequired`: the roles whose module declares `container.healthPath`), `ci.setup`, `detect`, `vscode` (`launch` as data, `values`, `label`, `optional`), `migrations`, `compose` (the local
stack; `opsModules` its registry rows).

| Driver | Package | Release runs | Remote dev |
|---|---|---|---|
| `dotnet-aspnet` (api, worker) | `dotnet publish` into `{out}` | `container/Dockerfile` on the ASP.NET runtime | `dotnet watch` in the SDK image |
| `dotnet-library` | none: a class library is built and tested, never packaged (not deployable) | none | none |
| `java-boot` | `build`, the boot jar | `container/Dockerfile` on a JRE | `bootRun` in a JDK image; Java sources `rebuild` |
| `node-api` | `build`, `dist/**` + manifest + lockfile | `container/Dockerfile`, production dependencies | the `dev` script |
| `node-spa`, `node-vite` | `build`, `dist/**` | an image built from the shared recipe (`drivers/_shared/static/Dockerfile`): pinned unprivileged nginx serving `serve` (SPA routes to `index.html`), its rendered `server.conf` COPYed in | the `start` / `dev` script |

Adding a driver: copy `drivers/_template/`, declare it in `drivers/registry.json` (or the host's own
registry), give it a `container` recipe and a `dev`; nothing else changes. Per-driver detail:
[dotnet-aspnet](../drivers/dotnet-aspnet/README.md), [dotnet-library](../drivers/dotnet-library/README.md), [java-boot](../drivers/java-boot/README.md),
[node-api](../drivers/node-api/README.md), [node-spa](../drivers/node-spa/README.md),
[node-vite](../drivers/node-vite/README.md), [drivers/README.md](../drivers/README.md).

## Security, data and extension

| Declared in | Does | Verb |
|---|---|---|
| `config.keys` rows' `policy` | the env values a release must hold (required, minLength, format, forbid, requires); `generate` makes a value on the server once, given as `<NAME>_FILE` | `config check`, every `deploy` |
| `security` | `allow`, `knownLeaks` (sha256 fingerprints) for the secret scan; `imageScan` (a digest-pinned scanner, failOn, observeOnly, maxDbAgeHours, vex) | `scan secrets [--history]`, every `deploy` |
| `stack.infra.backup.<store>` | `keep`, `anchors` a throwaway restore must hold | `backup`, `backup verify`, `backup list` |
| `stack.migrate` | the one-shot migration service a release runs before the apps; `migrations lock` keeps the checksum ledger | `deploy`, `migrations` |
| `ci.database` | the test database a module's CI job runs beside | `ci-gen` |
| `targets.<t>.oidc` | the OIDC provider `targets --health` checks (discovery, JWKS) | `targets --health` |
| `config/extension-points.json` | every place a host extends the kit; pending answers, 3-way upgrades | `extend` |
| `config/conformance.json` | each standard clause, its mechanism, evidence and status (machine-checked) | -- |

TLS on a private network: `tls ca`, `tls leaf <host>`, `tls truststore` (the CA on the target, the
edge template reads the leaves). A shared host's disk: `ops prune [--schedule]`.

## Resolver

One resolver (ADR-001 decision 2): `lib/resolution/` answers what the manifest says (one flat
context) and the environment's answers (env files and values, the selected target, ssh options);
shells ask it through `lib/resolve_cli.py` and hold no rule (`tests/acceptance/test_resolver_parity.py`).
Remote paths are never its answer: only the engine renders them, for the CLI's verbs.

| Question | Answer |
|---|---|
| Project root | `STACK_KIT_PROJECT_ROOT` if set; else the working directory and its parents holding `stack-kit.json` |
| Env value of a secrets folder | last non-empty across `.env`, then `.env.<environment>` in catalog order |
| A run's environment | `.env`, then `.env.<environment>` (default the catalog's run default) |
| Deploy target | `--target`, else `defaults.<environment>`, else the only one; a pending target refuses every remote verb with its reason |
| Names | `lib/naming.py`: `{project}-{service}` locally; `{project}-{environment}`, `{project}-{environment}-{service}`, `...:{release}` on a server |

## Environment variables

| Variable | Meaning |
|---|---|
| `STACK_KIT_PROJECT_ROOT` | host root; authoritative when set |
| `STACK_KIT_KIT_ROOT` | kit root; set by the CLI |
| `STACK_KIT_TARGET`, `STACK_KIT_ENVIRONMENT` | what `--target` / `--env` set for every child process |
| `STACK_KIT_MODULE_ID`, `STACK_KIT_COMMAND` | the module and command a driver script runs for |
| `STACK_KIT_TRANSPORT` | `record:<file>` or `local:<dir>`: a rehearsal server (tests) |
| `STACK_KIT_LEGACY_ROOT_DISCOVERY=1` | allow pre-v2 root discovery |
