---
kind: guide
authority: canonical
owns: adoption
---

# Adopt stack-kit

Taking a host onto the kit, once it is vendored ([INSTALL.md](INSTALL.md)). Field-by-field
manifest and command detail is [REFERENCE.md](REFERENCE.md); the day-to-day paths are
[GOLDEN-PATHS.md](GOLDEN-PATHS.md). Reference host: `tests/fixtures/golden-consumer/`.

## Package vs project

| Artifact | Kit (`kits/stack-kit`) | Host (repo root) |
|---|---|---|
| `stack-kit.json` | schema `manifest.schema.json`, template `scaffold/stack-kit.json` | **the instance** |
| `ops/config/` (env, `deploy.env`, SSH) | `*.example` in `scaffold/` | **real values, gitignored** |
| `ops/compose/catalog.json` | `scaffold/ops/compose/catalog.{minimal,full}.json` | **the stack definition** |
| `ops/compose/infra/` | `toolkit/infra/Invoke-Infra.ps1`, `compose/infra-catalog.json` | `docker-compose.base.yml`, `services/*.yml`, `ops/config/infra/.env.*` |
| `docker-compose*.yml` | the generator (`compose/build.py`) | **generated** under `apps/*`, `ops/compose/stack/` |
| `ops.modules` (java-boot) | `compose/sync_ops_modules.py` | **generated** at `compose.syncModules` |
| `nginx.conf.template` | `adapters/render_nginx.py` | under the UI module + `ops/config/<ui>/nginx.env` |
| deploy / manage scripts | `toolkit/`, `drivers/` | called through `tools/stack-kit.ps1` |
| CI | `ci/prepare-integration-env.sh`, `ci/wait-health.sh`, `ci/wait-stack-health.sh` | `ops/ci/integration-stack.sh`, `.github/workflows/` |
| domain code | — | `apps/*` only |

Rule: names your domain, an API key or a business module → host. Works for any SSH + Docker +
Gradle/npm monorepo → kit.

## Target layout

```text
<host>/                         ← STACK_KIT_PROJECT_ROOT
├── stack-kit.json              ← the contract (required)
├── tools/stack-kit.ps1 | .cmd  ← launchers (INSTALL.md#launchers)
├── kits/stack-kit/             ← the kit (submodule or copy)
├── ops/
│   ├── cli/stack-kit.ps1 | .sh ← canonical entry
│   ├── config/                 ← manifest `secrets`; values gitignored
│   │   ├── deploy.env
│   │   ├── ssh/
│   │   ├── infra/.env.dev | .env.prod
│   │   └── <secretsModule>/    ← .env.dev, .env.prod, .env.deploy, credential files
│   ├── compose/
│   │   ├── catalog.json
│   │   ├── infra/              ← docker-compose.base.yml + services/*.yml
│   │   └── stack/              ← GENERATED full-stack compose
│   └── ci/integration-stack.sh
└── apps/
    ├── frontend/  ops.config.ps1, docker-compose*.yml (GENERATED), nginx.conf.template, src/
    └── backend/   ops.config.sh, ops.modules (GENERATED), docker-compose.*.yml (GENERATED), src/
```

## Bootstrap with init

`stack-kit init` (`toolkit/init/Invoke-ProjectInit.ps1`; first run from bash: `bash kits/stack-kit/toolkit/init/init.sh [<root>]`, since `cli/stack-kit.sh` stops when no manifest exists yet), in order:

1. Scaffold: `tools/`, `ops/cli/`, `ops/ci/`, `ops/config/*.example`, `ops/compose/`, `apps/*` (ops files only), `stack-kit.json` — merged, never over real secrets.
2. Catalog: `catalog.full.json` → `ops/compose/catalog.json` (`-MinimalCatalog`: `catalog.minimal.json`, API only).
3. Seed `ops/config/` per manifest module (`lib/ci_prepare.py`): `.example` → `deploy.env`, `.env.dev`, `.env.prod`, `.env.deploy`, `nginx.env`; `COMPOSE_PROJECT_NAME` / network from the repo folder.
4. Merge `.gitignore` rules.
5. `compose-gen`.
6. `vscode-gen` (missing `.vscode` files only).
7. `nginx-gen` when `adapters.nginx.template` exists.
8. Checklist of values still to fill.

| Flag | Effect |
|---|---|
| `-MinimalCatalog` | `catalog.minimal.json` instead of the full catalog |
| `-SkipComposeGen` | no compose-gen |
| `-SkipSeed` | no env files from examples |
| `-SkipNginxGen` | no nginx-gen |
| `-SkipGitIgnore` | leave `.gitignore` alone |
| `-ForceExamples` | overwrite existing scaffold/env files and the catalog from examples |

Without `-ForceExamples`, existing `deploy.env`, `.env.*` and SSH keys are never overwritten.
Tree only, no seed: `powershell -ExecutionPolicy Bypass -File kits\stack-kit\scaffold\apply-scaffold.ps1`
(bash: `scaffold/apply-scaffold.sh <root>`). Not part of init: application code. More: [toolkit/init/README.md](../toolkit/init/README.md), [scaffold/README.md](../scaffold/README.md).

## The manifest

`stack-kit.json` at the host root; start from `scaffold/stack-kit.json` (init copies it). Set
`"$schema": "./kits/stack-kit/manifest.schema.json"`. Edit at least:

| Field | Value |
|---|---|
| `version` | `2` (schema minimum) |
| `package` | `"kits/stack-kit"` |
| `secrets` | `"ops/config"` |
| `modules.<id>.type` | driver id from `drivers/registry.json` — always explicit, never inferred from a folder name |
| `modules.<id>.role` | `ui`, `api`, `worker`, `gateway`, `data`, `other` |
| `modules.<id>.path` | app tree, e.g. `apps/frontend` |
| `modules.<id>.secretsModule` | folder under `ops/config/` (usually the module id) |
| `cli.aliases` | shortcuts, e.g. `{ "fe": "frontend", "be": "backend" }` |

Every section, credentials, stack deploy, CI health, hybrid: [REFERENCE.md#manifest](REFERENCE.md#manifest).
Check with `stack-kit validate`.

## Configuration

`ops/config/` (manifest `secrets`) holds real values; `.gitignore`: `ops/config/**` except `*.example`.

```powershell
copy kits\stack-kit\scaffold\ops\config\deploy.env.example ops\config\deploy.env
# per module: ops/config/<secretsModule>/.env.example → .env.dev / .env.prod
```

| File | Typical keys |
|---|---|
| `ops/deploy/targets.json` (tracked) | the deploy targets: `host`, `user`, `port`, `root`, `runtime`, `ssh` (identity reference, pinned `known_hosts`), `layout`; per machine `targets.local.json` (ignored). [REFERENCE.md#manifest](REFERENCE.md#manifest) `deploy` |
| `ops/config/deploy.env` | `DEPLOY_PROJECT`, `COMPOSE_PROJECT_NAME`, `DOCKER_NETWORK`. Its former `DEPLOY_SERVER`, `DEPLOY_SERVER_BASE`, `DEPLOY_SSH_*` are read until 2.0.0 when no target is declared; `migrate --apply` declares them as one |
| `ops/config/<ui>/.env.dev` | `VITE_API_URL=http://localhost:8090` |
| `ops/config/<ui>/.env.deploy` | `DEPLOY_HOST_PORT=5177`, `DEPLOY_PATH`, `DEPLOY_LAYOUT=structured` |
| `ops/config/<api>/.env.dev` | `API_PORT=8090`, the module's keys |
| `ops/config/<api>/.env.prod` | prod keys, `API_INTERNAL_URL` for a worker |
| `ops/config/infra/.env.dev` | infra ports/credentials (`.env.prod` with `-Prod`) |
| `ops/config/ssh/` | project-local SSH key + `config` ([scaffold/ops/config/ssh/README.md](../scaffold/ops/config/ssh/README.md)) |

Defaults when unset (`lib/deploy-defaults.json`): `DEPLOY_PROJECT`, `COMPOSE_PROJECT_NAME` = repo folder;
`DOCKER_NETWORK` = `{slug}-net`; `API_PORT` 8090; `WORKER_PORT` 8091; `DEPLOY_HOST_PORT` 5177.
A server already running the old container names: merge `scaffold/ops/config/profiles/legacy-server.env.example`
into `deploy.env`, then `compose-gen`. Credential profiles: `scaffold/ops/config/profiles/`.

## Compose catalog

`ops/compose/catalog.json` is the host's one source for which services are generated where.

1. Start from `scaffold/ops/compose/catalog.minimal.json` (or the full one init copies).
2. Add `templates` (YAML fragments) and `targets` (which file receives which services); `manifestStack` / `manifestModule` targets render manifest modules.
3. Embedded backend worker: `modules.<api>.compose.embeddedWorker` (catalog `features.worker` is deprecated; `validate` warns). Use `false` when the worker is its own `role: worker` module — never both.
4. Service names come from the manifest (`lib/compose_identity.py`); `deploy.env` `COMPOSE_*_SERVICE` only in the legacy profile.

```powershell
.\tools\stack-kit.ps1 compose-gen
```

Generated (never edit a file starting `# GENERATED`): `apps/*/docker-compose*.yml`, `ops/compose/stack/*.yml`, `apps/backend/ops.modules`.

## Module files

UI module (`node-vite`, e.g. `apps/frontend/`):

| File | Purpose |
|---|---|
| `ops.config.ps1` | `$OpsSecretsModule = "<secretsModule>"`, `$OpsComposeFile = "docker-compose.yml"`; optional `$OpsDevSyncExcludes`, `$OpsDevWatchPaths`, `$OpsDevComposeDevFiles`, `$OpsDevSyncExtraPaths` (template `toolkit/templates/ops.config.ps1.example`) |
| `docker-compose.yml` / `.override.yml` / `.prod.yml` | base (may be GENERATED) / dev overlay / prod overlay |
| `src/Dockerfile` | multi-stage: dev + production targets ([GOLDEN-PATHS.md#remote-dev-dockerfile-flow](GOLDEN-PATHS.md#remote-dev-dockerfile-flow)) |
| `package.json` | `npm run build` → `dist/` |
| `nginx.conf.template` | when `adapters.nginx` is declared |
| `logs/` | ops logs (empty + `.gitignore`) |

The UI holds no deploy logic: app + Dockerfile only; the rest is `drivers/node-vite/`.

API module (`java-boot`, e.g. `apps/backend/`):

| File | Purpose |
|---|---|
| `ops.config.sh` | `OPS_SECRETS_MODULE`, `OPS_PROJECT_NAME`, `OPS_TARGET_DEFAULT`, `VERSIONS_KEEP=5`, `HEALTH_RETRIES=24`, `CRED_PATTERNS` (template `toolkit/templates/ops.config.sh.example`) |
| `ops.modules` | GENERATED Gradle subproject registry, lines `<service>=<gradle-project>:<sub>` |
| `docker-compose.dev.yml` / `.prod.yml` | GENERATED |
| `gradlew`, `settings.gradle` | multi-module build |
| `src/Dockerfile`, `src/Dockerfile.dev`, `src/Dockerfile.dev.remote` | [GOLDEN-PATHS.md#remote-dev-jar-flow](GOLDEN-PATHS.md#remote-dev-jar-flow) |
| `worker/` | optional embedded worker |
| `logs/` | deploy/manage logs |

## CI

Recommended jobs (`.github/workflows/ci.yml`):

| Job | Checks |
|---|---|
| `compose-catalog` | `python3 kits/stack-kit/compose/build.py` + `git diff` on GENERATED yaml |
| `ops-scripts` | Python compile, `shellcheck` drivers/toolkit, catalog JSON valid |
| `frontend-build` | `npm ci && npm run build` (with CI `VITE_API_URL`) |
| `backend-build` | `./gradlew build` |
| `integration-compose` | `prepare-integration-env.sh` + `ops/ci/integration-stack.sh` |

`ops/ci/integration-stack.sh`: copy `scaffold/ops/ci/integration-stack.sh` (init does). It finds the
api module from the manifest (role `api`, else type `java-boot`), seeds env
(`ci/prepare-integration-env.sh` → `lib/ci_prepare.py`), runs compose-gen, starts the dev compose and
waits on health (`ci/wait-health.sh <url> <expect> <seconds>`; all modules: `ci/wait-stack-health.sh`).
Manifest `ci.*` paths must match the files. Health targets: [REFERENCE.md#manifest](REFERENCE.md#manifest) (`ci.healthModules`).

Before a PR, locally:

```powershell
.\tools\stack-kit.ps1 compose-gen
git diff --exit-code **/docker-compose*.yml
.\tools\stack-kit.ps1 be check
.\tools\stack-kit.ps1 fe check
bash ops/ci/integration-stack.sh      # when Docker is available
```

## Adoption checklist

- [ ] `stack-kit.json` at the root with `$schema`; `stack-kit validate` clean
- [ ] `.\tools\stack-kit.ps1 help` lists the modules and types
- [ ] `ops/config/deploy.env` exists locally, not committed
- [ ] `ops/compose/catalog.json` is valid JSON
- [ ] `compose-gen` run; GENERATED files committed
- [ ] each UI module has `ops.config.ps1`, each bash-driver module `ops.config.sh`
- [ ] `.\tools\stack-kit.ps1 stack up -d --build` brings UI + API up locally
- [ ] CI workflow added; `ops/ci/integration-stack.sh` green

## Moving an existing host

| Situation | Do |
|---|---|
| Host on the former kit names | Former names and their replacements: [CHANGELOG.md](../CHANGELOG.md) 1.2.0-dev, "Identity". They are read, with one notice each, until 2.0.0; `STACK_KIT_NO_DEPRECATION_NOTICE=1` silences the notices. |
| Manifest before v2, or former names | `stack-kit migrate` (dry run) → `stack-kit migrate --apply` → `stack-kit validate`. Raises `version` to 2, adds missing `role`s (from the driver's declared role), renames the manifest file and renamed fields; refuses a host holding both manifest names; prints, never rewrites, each line of the host's own files that still spells a former name. |
| Pre-v2 tree without a manifest | `STACK_KIT_LEGACY_ROOT_DISCOVERY=1` finds the root by `ops/config` or `secrets/` next to a vendored kit — a bridge until `stack-kit.json` exists. |
| Flat server layout | [GOLDEN-PATHS.md#layout-migration](GOLDEN-PATHS.md#layout-migration). |
| New stack type (Go, FastAPI, Next.js, …) | A new driver, never a renamed folder: [REFERENCE.md#drivers](REFERENCE.md#drivers). |

## Maturity

Release gate for the kit, and the bar for making it required for new hosts. Every row passes →
ready for multi-module hosts with optional multi-credential profiles.

| Area | Check | How |
|---|---|---|
| Boundary | no consumer names, no hardcoded `ops/config/frontend\|backend`, no hardcoded `google-credentials.json` in `toolkit/deploy/` | `pytest tests/unit/test_toolkit_hardcodes.py tests/unit/test_declared_agnosticism.py tests/acceptance/test_identity.py` |
| Boundary | root = `stack-kit.json` | `ProjectContext.discover()` |
| Manifest | schema valid; every module has `role`, `type`, `path`, `secretsModule`; types in `drivers/registry.json`; declared places exist; migrations carry no data | `stack-kit validate` |
| Real stack | `validate.stages` ends on a value anchor | `stack-kit validate --stages` |
| Manifest | legacy trees migrated | `stack-kit migrate --apply` (one time) |
| Credentials | per-module `modules.<id>.credentials[]`; global `features.gcpCredentials` + `adapters.gcp`; dev-remote / upload / ci_prepare use `lib/credentials.py` | `pytest tests/unit/test_credentials.py` |
| CI | host script manifest-driven; kit helpers `ci/*`; golden fixture | `ops/ci/integration-stack.sh`, `tests/fixtures/golden-consumer/` |
| Release | `VERSION` (semver), `CHANGELOG.md`, tag `v$(cat VERSION)` | `pytest tests/unit/test_release.py` |
| Dev modes | every mode smoke-tested | [GOLDEN-PATHS.md#smoke](GOLDEN-PATHS.md#smoke) |
| Local debug | `launch.json` + `tasks.json` from `modules.*.path`; Java Extension Pack for Spring breakpoints | `stack-kit vscode-gen` |

Full verification from the host root:

```bash
(cd kits/stack-kit && PYTHONPATH=. pytest tests -q)
python3 kits/stack-kit/lib/validate_manifest.py
bash kits/stack-kit/ci/prepare-integration-env.sh
bash ops/ci/integration-stack.sh      # optional, needs Docker
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `stack-kit.json not found (run: stack-kit init)` | run from inside the host, or set `STACK_KIT_PROJECT_ROOT` |
| `Unknown driver type` | add the type to `drivers/registry.json` + `drivers/<type>/` |
| `modules.*.type is required` | write `type` on the module |
| `Unknown module: <id>` / `Unknown subcommand` | module ids are `modules.*` keys; valid subcommands are the driver's `commands` (`stack-kit help` lists them) |
| `compose-gen` fails | install Python; run from the host root |
| GENERATED drift in CI | `stack-kit compose-gen`, commit |
| `Git Bash required` | install Git for Windows (bash drivers, `stack-deploy`, `layout migrate`) |
| backend deploy finds no modules | check `ops.modules` and `compose.syncModules` |
