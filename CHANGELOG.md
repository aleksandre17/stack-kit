# Changelog — geostat-kit

## 1.2.0-dev — unreleased

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
