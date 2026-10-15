# Changelog — stack-kit

## 1.2.0-dev — unreleased

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
